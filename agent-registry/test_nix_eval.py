import json
import os
import subprocess
import unittest


class TestAgentRegistryNixEval(unittest.TestCase):
    def test_devvm_app_and_home_manager_module_evaluate(self):
        repo = os.path.dirname(os.path.dirname(__file__))
        expr = f'''
let
  registry = builtins.getFlake "path:{repo}/agent-registry";
  root = builtins.getFlake "path:{repo}";
  system = "x86_64-linux";
  pkgs = import registry.inputs.nixpkgs {{ inherit system; }};
  hm = root.inputs.home-manager;
  cfg = hm.lib.homeManagerConfiguration {{
    inherit pkgs;
    modules = [
      registry.homeManagerModules.default
      {{
        home.username = "u";
        home.homeDirectory = "/tmp/u";
        home.stateVersion = "24.05";
        services.agent-registry = {{
          enable = true;
          auth = false;
          managedAgents.demo = {{
            command = "pi";
          }};
        }};
      }}
    ];
  }};
in builtins.toJSON {{
  devvmProgram = registry.apps.${{system}}.devvm.program;
  hasUserService = cfg.config.systemd.user.services ? agent-registry;
  hasManagedTimer = cfg.config.systemd.user.timers ? agent-registry-managed-demo;
}}
'''
        out = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expr], text=True).strip()
        data = json.loads(out)
        self.assertIn("agent-registry-devvm", data["devvmProgram"])
        self.assertTrue(data["hasUserService"])
        self.assertTrue(data["hasManagedTimer"])


if __name__ == "__main__":
    unittest.main()
