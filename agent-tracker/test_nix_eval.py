import json
import os
from pathlib import Path
import subprocess
import unittest


class TestNixEval(unittest.TestCase):
    def test_agent_tracker_enable_default_registry_settings_evaluates(self):
        repo = Path(__file__).resolve().parents[1]
        expr = f'''
let
  flake = builtins.getFlake "path:{repo}";
  system = builtins.currentSystem;
  pkgs = import flake.inputs.nixpkgs {{ inherit system; }};
  hm = flake.inputs.home-manager;
  cfg = hm.lib.homeManagerConfiguration {{
    inherit pkgs;
    modules = [
      ({{ lib, ... }}: {{
        options.programs.tmux.statusBar.extraLines = lib.mkOption {{ type = lib.types.listOf lib.types.anything; default = []; }};
      }})
      {repo}/agent-tracker/default.nix
      {{ services.agent-tracker.enable = true; home.username = "u"; home.homeDirectory = "/tmp/u"; home.stateVersion = "24.05"; }}
    ];
    extraSpecialArgs = {{ userSettings = {{ }}; }};
  }};
in builtins.toJSON cfg.config.services.agent-tracker.registryAuth
'''
        out = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expr], text=True).strip()
        self.assertEqual(out, "false")

    def test_agent_tracker_user_settings_single_registry_list_evaluates(self):
        repo = Path(__file__).resolve().parents[1]
        expr = f'''
let
  flake = builtins.getFlake "path:{repo}";
  system = builtins.currentSystem;
  pkgs = import flake.inputs.nixpkgs {{ inherit system; }};
  hm = flake.inputs.home-manager;
  cfg = hm.lib.homeManagerConfiguration {{
    inherit pkgs;
    modules = [
      ({{ lib, ... }}: {{
        options.programs.tmux.statusBar.extraLines = lib.mkOption {{ type = lib.types.listOf lib.types.anything; default = []; }};
      }})
      {repo}/agent-tracker/default.nix
      {{ home.username = "u"; home.homeDirectory = "/tmp/u"; home.stateVersion = "24.05"; }}
    ];
    extraSpecialArgs = {{
      userSettings = {{
        enable-agent-tracker = true;
        agent-tracker = {{
          registries = [
            {{ name = "mundus"; url = "https://agents.mundus.in"; }}
          ];
          registry-auth = false;
          http-port = 29876;
          registry-heartbeat-seconds = 45;
        }};
      }};
    }};
  }};
in builtins.toJSON {{
  enable = cfg.config.services.agent-tracker.enable;
  registries = cfg.config.services.agent-tracker.registries;
  registryAuth = cfg.config.services.agent-tracker.registryAuth;
  httpPort = cfg.config.services.agent-tracker.httpPort;
  registryHeartbeatSeconds = cfg.config.services.agent-tracker.registryHeartbeatSeconds;
}}
'''
        out = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expr], text=True).strip()
        data = json.loads(out)
        self.assertTrue(data["enable"])
        self.assertEqual(data["registries"], [
            {"name": "mundus", "token-file": None, "url": "https://agents.mundus.in"},
        ])
        self.assertFalse(data["registryAuth"])
        self.assertEqual(data["httpPort"], 29876)
        self.assertEqual(data["registryHeartbeatSeconds"], 45)

    def test_agent_tracker_user_settings_multiple_registries_evaluate(self):
        repo = Path(__file__).resolve().parents[1]
        expr = f'''
let
  flake = builtins.getFlake "path:{repo}";
  system = builtins.currentSystem;
  pkgs = import flake.inputs.nixpkgs {{ inherit system; }};
  hm = flake.inputs.home-manager;
  cfg = hm.lib.homeManagerConfiguration {{
    inherit pkgs;
    modules = [
      ({{ lib, ... }}: {{
        options.programs.tmux.statusBar.extraLines = lib.mkOption {{ type = lib.types.listOf lib.types.anything; default = []; }};
      }})
      {repo}/agent-tracker/default.nix
      {{ home.username = "u"; home.homeDirectory = "/tmp/u"; home.stateVersion = "24.05"; }}
    ];
    extraSpecialArgs = {{
      userSettings = {{
        enable-agent-tracker = true;
        agent-tracker = {{
          registries = [
            {{ name = "corp"; url = "https://corp.example"; token-file = "/tmp/corp-token"; }}
            {{ name = "lab"; url = "https://lab.example"; }}
          ];
        }};
      }};
    }};
  }};
in builtins.toJSON {{
  registries = cfg.config.services.agent-tracker.registries;
}}
'''
        out = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expr], text=True).strip()
        data = json.loads(out)
        self.assertEqual(data["registries"], [
            {"name": "corp", "token-file": "/tmp/corp-token", "url": "https://corp.example"},
            {"name": "lab", "token-file": None, "url": "https://lab.example"},
        ])

    def test_agent_tracker_capture_pane_default_lines_user_setting_evaluates(self):
        repo = Path(__file__).resolve().parents[1]
        expr = f'''
let
  flake = builtins.getFlake "path:{repo}";
  system = builtins.currentSystem;
  pkgs = import flake.inputs.nixpkgs {{ inherit system; }};
  hm = flake.inputs.home-manager;
  cfg = hm.lib.homeManagerConfiguration {{
    inherit pkgs;
    modules = [
      ({{ lib, ... }}: {{
        options.programs.tmux.statusBar.extraLines = lib.mkOption {{ type = lib.types.listOf lib.types.anything; default = []; }};
      }})
      {repo}/agent-tracker/default.nix
      {{ home.username = "u"; home.homeDirectory = "/tmp/u"; home.stateVersion = "24.05"; }}
    ];
    extraSpecialArgs = {{
      userSettings = {{
        enable-agent-tracker = true;
        agent-tracker = {{
          capture-pane-default-lines = 42;
        }};
      }};
    }};
  }};
in builtins.toJSON cfg.config.services.agent-tracker.capturePaneDefaultLines
'''
        out = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expr], text=True).strip()
        self.assertEqual(out, "42")

    def test_darwin_launchd_agent_is_run_at_load_without_keepalive_loop(self):
        repo = Path(__file__).resolve().parents[1]
        expr = f'''
let
  flake = builtins.getFlake "path:{repo}";
  pkgs = import flake.inputs.nixpkgs {{ system = "aarch64-darwin"; }};
  hm = flake.inputs.home-manager;
  cfg = hm.lib.homeManagerConfiguration {{
    inherit pkgs;
    modules = [
      ({{ lib, ... }}: {{
        options.programs.tmux.statusBar.extraLines = lib.mkOption {{ type = lib.types.listOf lib.types.anything; default = []; }};
      }})
      {repo}/agent-tracker/default.nix
      {{ services.agent-tracker.enable = true; home.username = "u"; home.homeDirectory = "/Users/u"; home.stateVersion = "24.05"; }}
    ];
    extraSpecialArgs = {{ userSettings = {{ }}; }};
  }};
  agent = cfg.config.launchd.agents.agent-tracker.config;
in builtins.toJSON {{
  keepAlive = agent.KeepAlive;
  runAtLoad = agent.RunAtLoad;
  programArguments = agent.ProgramArguments;
  environment = agent.EnvironmentVariables;
  stdout = agent.StandardOutPath;
  stderr = agent.StandardErrorPath;
}}
'''
        out = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expr], text=True).strip()
        data = json.loads(out)
        self.assertFalse(data["keepAlive"])
        self.assertTrue(data["runAtLoad"])
        self.assertEqual(len(data["programArguments"]), 1)
        self.assertIn("AGENT_TRACKER_SOCKET", data["environment"])
        self.assertIn("PATH", data["environment"])
        self.assertTrue(data["stdout"].endswith("/agent-tracker/launchd.stdout.log"))
        self.assertTrue(data["stderr"].endswith("/agent-tracker/launchd.stderr.log"))


if __name__ == "__main__":
    unittest.main()
