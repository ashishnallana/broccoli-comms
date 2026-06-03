package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sort"
	"time"

	lua "github.com/yuin/gopher-lua"
)

func luaToGo(value lua.LValue) any {
	switch v := value.(type) {
	case lua.LBool:
		return bool(v)
	case lua.LNumber:
		return float64(v)
	case lua.LString:
		return string(v)
	case *lua.LTable:
		max := 0
		count := 0
		isArray := true
		v.ForEach(func(key lua.LValue, _ lua.LValue) {
			count++
			n, ok := key.(lua.LNumber)
			if !ok || float64(int(n)) != float64(n) || int(n) < 1 {
				isArray = false
				return
			}
			if int(n) > max {
				max = int(n)
			}
		})
		if isArray && count == max {
			out := make([]any, max)
			for i := 1; i <= max; i++ {
				out[i-1] = luaToGo(v.RawGetInt(i))
			}
			return out
		}
		out := map[string]any{}
		v.ForEach(func(key lua.LValue, item lua.LValue) {
			out[key.String()] = luaToGo(item)
		})
		return out
	case *lua.LNilType:
		return nil
	default:
		return value.String()
	}
}

func goToLua(L *lua.LState, value any) lua.LValue {
	switch v := value.(type) {
	case nil:
		return lua.LNil
	case bool:
		return lua.LBool(v)
	case float64:
		return lua.LNumber(v)
	case string:
		return lua.LString(v)
	case []any:
		t := L.NewTable()
		for i, item := range v {
			t.RawSetInt(i+1, goToLua(L, item))
		}
		return t
	case map[string]any:
		t := L.NewTable()
		keys := make([]string, 0, len(v))
		for key := range v {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			t.RawSetString(key, goToLua(L, v[key]))
		}
		return t
	default:
		return lua.LString(fmt.Sprint(v))
	}
}

func jsonAdapter(L *lua.LState) *lua.LTable {
	adapter := L.NewTable()
	adapter.RawSetString("encode", L.NewFunction(func(L *lua.LState) int {
		data, err := json.Marshal(luaToGo(L.Get(1)))
		if err != nil {
			L.RaiseError("json encode failed: %v", err)
		}
		L.Push(lua.LString(data))
		return 1
	}))
	adapter.RawSetString("decode", L.NewFunction(func(L *lua.LState) int {
		var value any
		if err := json.Unmarshal([]byte(L.CheckString(1)), &value); err != nil {
			L.RaiseError("json decode failed: %v", err)
		}
		L.Push(goToLua(L, value))
		return 1
	}))
	return adapter
}

func unixRequest(socketPath string, payload string, timeoutMS int) (string, error) {
	timeout := time.Duration(timeoutMS) * time.Millisecond
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	conn, err := net.DialTimeout("unix", socketPath, timeout)
	if err != nil {
		return "", err
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(timeout))
	if _, err := conn.Write([]byte(payload)); err != nil {
		return "", err
	}
	if unixConn, ok := conn.(*net.UnixConn); ok {
		_ = unixConn.CloseWrite()
	}
	var buf bytes.Buffer
	if _, err := buf.ReadFrom(conn); err != nil {
		return "", err
	}
	return buf.String(), nil
}

func fakeRequest(payload string) string {
	var req map[string]any
	_ = json.Unmarshal([]byte(payload), &req)
	method, _ := req["method"].(string)
	var result any
	switch method {
	case "list":
		result = map[string]any{"demo-agent": map[string]any{"name": "demo-agent", "status": "idle", "scope": "local"}}
	case "send_message":
		result = true
	case "get_inbox":
		result = map[string]any{"mode": "last_n", "messages": []any{}}
	default:
		body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": req["id"], "error": map[string]any{"code": -32601, "message": "Method not found"}})
		return string(body)
	}
	body, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": req["id"], "result": result})
	return string(body)
}

func transportAdapter(L *lua.LState, fake bool) *lua.LTable {
	adapter := L.NewTable()
	adapter.RawSetString("request", L.NewFunction(func(L *lua.LState) int {
		socketPath := L.CheckString(1)
		payload := L.CheckString(2)
		timeoutMS := L.CheckInt(3)
		var response string
		var err error
		if fake {
			response = fakeRequest(payload)
		} else {
			response, err = unixRequest(socketPath, payload, timeoutMS)
		}
		if err != nil {
			failure := L.NewTable()
			failure.RawSetString("kind", lua.LString("transport"))
			failure.RawSetString("message", lua.LString(err.Error()))
			L.Push(lua.LNil)
			L.Push(failure)
			return 2
		}
		L.Push(lua.LString(response))
		return 1
	}))
	return adapter
}

func tableWithString(L *lua.LState, key string, value string) *lua.LTable {
	t := L.NewTable()
	t.RawSetString(key, lua.LString(value))
	return t
}

func callClient(L *lua.LState, client lua.LValue, method string, opts *lua.LTable) (lua.LValue, lua.LValue, error) {
	fn := L.GetTable(client, lua.LString(method))
	if err := L.CallByParam(lua.P{Fn: fn, NRet: 2, Protect: true}, client, opts); err != nil {
		return lua.LNil, lua.LNil, err
	}
	errValue := L.Get(-1)
	result := L.Get(-2)
	L.Pop(2)
	return result, errValue, nil
}

func main() {
	command := flag.String("command", "list", "list, send-message, or read-inbox")
	socketPath := flag.String("socket", "/tmp/agent-tracker.sock", "agent-tracker Unix socket path")
	luaDir := flag.String("lua-dir", filepath.Join("..", ".."), "path containing broccoli Lua modules")
	timeoutMS := flag.Int("timeout-ms", 5000, "request timeout in milliseconds")
	fake := flag.Bool("fake", false, "use an in-process fake tracker response")
	target := flag.String("target", "demo-agent", "target for send-message")
	message := flag.String("message", "hello from Go Lua demo", "message for send-message")
	agentName := flag.String("agent-name", "agent-communicator", "agent name for read-inbox")
	flag.Parse()

	L := lua.NewState()
	defer L.Close()
	packageTable := L.GetGlobal("package").(*lua.LTable)
	oldPath := packageTable.RawGetString("path").String()
	packageTable.RawSetString("path", lua.LString(filepath.Join(*luaDir, "?.lua")+";"+filepath.Join(*luaDir, "?", "init.lua")+";"+oldPath))

	if err := L.CallByParam(lua.P{Fn: L.GetGlobal("require"), NRet: 1, Protect: true}, lua.LString("broccoli.tracker")); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	trackerModule := L.Get(-1).(*lua.LTable)
	L.Pop(1)
	newFn := trackerModule.RawGetString("new")
	opts := L.NewTable()
	opts.RawSetString("socket_path", lua.LString(*socketPath))
	opts.RawSetString("timeout_ms", lua.LNumber(*timeoutMS))
	opts.RawSetString("json", jsonAdapter(L))
	opts.RawSetString("transport", transportAdapter(L, *fake))
	if err := L.CallByParam(lua.P{Fn: newFn, NRet: 1, Protect: true}, opts); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	client := L.Get(-1)
	L.Pop(1)

	var callOpts *lua.LTable
	switch *command {
	case "list":
		callOpts = L.NewTable()
		callOpts.RawSetString("include_remote", lua.LBool(true))
	case "send-message":
		callOpts = tableWithString(L, "target", *target)
		callOpts.RawSetString("message", lua.LString(*message))
	case "read-inbox":
		callOpts = tableWithString(L, "agent_name", *agentName)
		callOpts.RawSetString("last", lua.LNumber(5))
	default:
		fmt.Fprintln(os.Stderr, "unknown command")
		os.Exit(2)
	}

	methodName := map[string]string{"list": "list", "send-message": "send_message", "read-inbox": "read_inbox"}[*command]
	result, errValue, err := callClient(L, client, methodName, callOpts)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if errValue != lua.LNil {
		body, _ := json.MarshalIndent(luaToGo(errValue), "", "  ")
		fmt.Println(string(body))
		os.Exit(1)
	}
	body, _ := json.MarshalIndent(luaToGo(result), "", "  ")
	fmt.Println(string(body))
}
