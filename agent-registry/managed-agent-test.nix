{ pkgs, self }:
let
  fakePi = pkgs.writeShellScriptBin "pi" ''
    exec ${pkgs.coreutils}/bin/sleep 300
  '';
in pkgs.testers.runNixOSTest {
  name = "agent-registry-managed-agent";

  nodes.machine = { pkgs, ... }: {
    imports = [ self.nixosModules.default ];

    users.users.tanmay = {
      isNormalUser = true;
      createHome = true;
      home = "/home/tanmay";
      packages = [ pkgs.tmux ];
    };

    services.agent-registry = {
      enable = true;
      auth = false;
      managedAgents.nixos-expert = {
        user = "tanmay";
        session = "nix-homelab-config";
        cwd = "~";
        command = "${fakePi}/bin/pi";
        wrapperPath = "${pkgs.coreutils}/bin/env";
        tmuxSocketPath = "/home/tanmay/.cache/agent-registry/tmux.sock";
        reconcileIntervalSeconds = 60;
        restart = {
          enable = true;
          intervalSeconds = 3600;
          warningLeadTimeSeconds = 2;
          warningMessage = "Restarting in 2 seconds";
        };
      };
    };
  };

  testScript = ''
    start_all()
    machine.wait_for_unit("agent-registry.service")
    machine.wait_for_unit("agent-registry-managed-nixos-expert.timer")
    machine.wait_for_unit("agent-registry-restart-nixos-expert.timer")

    socket = "/home/tanmay/.cache/agent-registry/tmux.sock"
    machine.succeed("systemctl start agent-registry-managed-nixos-expert.service")
    machine.wait_until_succeeds(f"su - tanmay -c 'tmux -S {socket} has-session -t nix-homelab-config'")
    machine.wait_until_succeeds(f"su - tanmay -c \"tmux -S {socket} list-panes -a -t nix-homelab-config -F '#{{@agent_name}}' | grep -x nixos-expert\"")

    machine.succeed(f"su - tanmay -c \"pane=\\$(tmux -S {socket} list-panes -a -t nix-homelab-config -F '#{{pane_id}} #{{@agent_name}}' | awk '\\$2 == \\\"nixos-expert\\\" {{print \\$1; exit}}'); tmux -S {socket} kill-pane -t \\\"\\$pane\\\"\"")
    machine.succeed("systemctl start agent-registry-managed-nixos-expert.service")
    machine.wait_until_succeeds(f"su - tanmay -c \"tmux -S {socket} list-panes -a -t nix-homelab-config -F '#{{@agent_name}}' | grep -x nixos-expert\"")

    before_pid = machine.succeed(f"su - tanmay -c \"tmux -S {socket} list-panes -a -t nix-homelab-config -F '#{{pane_pid}} #{{@agent_name}}' | awk '\\$2 == \\\"nixos-expert\\\" {{print \\$1; exit}}'\"").strip()
    machine.succeed("systemctl start agent-registry-restart-nixos-expert.service")
    machine.wait_until_succeeds(f"su - tanmay -c \"tmux -S {socket} list-panes -a -t nix-homelab-config -F '#{{@agent_name}}' | grep -x nixos-expert\"")
    after_pid = machine.succeed(f"su - tanmay -c \"tmux -S {socket} list-panes -a -t nix-homelab-config -F '#{{pane_pid}} #{{@agent_name}}' | awk '\\$2 == \\\"nixos-expert\\\" {{print \\$1; exit}}'\"").strip()
    assert before_pid != after_pid, f"expected restart to change pane pid, got {before_pid} == {after_pid}"
  '';
}
