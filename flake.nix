{
  description = "Standalone Broccoli Comms agent runtime";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      lib = nixpkgs.lib;
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      packages = forAllSystems (pkgs:
        let
          agentTrackerFiles = pkgs.stdenvNoCC.mkDerivation {
            pname = "broccoli-comms-agent-tracker-files";
            version = "0.1.0";
            src = ./agent-tracker;
            installPhase = ''
              runHook preInstall
              mkdir -p $out
              cp -R . $out/
              runHook postInstall
            '';
          };

          agentTracker = pkgs.writeShellApplication {
            name = "agent-tracker";
            runtimeInputs = with pkgs; [ python3 tmux coreutils gnugrep procps bash ];
            text = ''
              exec ${pkgs.python3}/bin/python3 ${agentTrackerFiles}/agent-tracker.py "$@"
            '';
          };

          agentWrapper = pkgs.writeShellApplication {
            name = "agent-wrapper";
            runtimeInputs = with pkgs; [ bash tmux coreutils gnugrep python3 procps ];
            text = builtins.readFile ./wrapper/agent-wrapper.sh;
          };

          agentTrackerCtl = pkgs.writeShellApplication {
            name = "agent-tracker-ctl";
            runtimeInputs = with pkgs; [ bash ];
            text = ''
              echo "agent-tracker-ctl is deprecated. Use: broccoli-comms agent-tracker <subcommand> [args...]" >&2
              exit 1
            '';
          };

          agentCommunicator = pkgs.buildGoModule {
            pname = "agent-communicator-tui";
            version = "0.1.0";
            src = ./agent-communicator-tui;
            vendorHash = null;
            ldflags = [ "-X main.version=0.1.0" ];
            postInstall = ''
              ln -sf $out/bin/agent-communicator-tui $out/bin/agent-communicator
            '';
          };

          agentRegistry = pkgs.writeShellApplication {
            name = "agent-registry";
            runtimeInputs = [ pkgs.python3 ];
            text = ''exec ${pkgs.python3}/bin/python3 ${./agent-registry/server.py} "$@"'';
          };

          managedAgent = pkgs.writeShellApplication {
            name = "agent-registry-managed-agent";
            runtimeInputs = with pkgs; [ python3 tmux coreutils procps bash ];
            text = ''exec ${pkgs.python3}/bin/python3 ${./agent-registry/managed_agent.py} "$@"'';
          };

          agentCommunicatorElectron = pkgs.buildNpmPackage {
            pname = "agent-communicator-electron";
            version = "0.1.0";
            src = ./agent-communicator-electron;
            npmDepsHash = "sha256-oJ5yK6jnb9wBtbsc1RAhckB2QVFXerANFkVMIva25+k=";

            env.ELECTRON_SKIP_BINARY_DOWNLOAD = "1";
            npmBuildScript = "build";

            installPhase = ''
              runHook preInstall

              mkdir -p $out/share/agent-communicator-electron $out/bin
              cp -R out package.json $out/share/agent-communicator-electron/

              makeWrapper ${pkgs.electron}/bin/electron $out/bin/agent-communicator-electron \
                --add-flags $out/share/agent-communicator-electron

              runHook postInstall
            '';

            nativeBuildInputs = [ pkgs.makeWrapper ];
          };

          broccoliComms = pkgs.writeShellApplication {
            name = "broccoli-comms";
            runtimeInputs = with pkgs; [ python3 tmux coreutils procps bash agentTracker agentTrackerCtl agentWrapper agentCommunicator agentRegistry ];
            text = ''
              export PATH=${lib.makeBinPath [ agentTracker agentTrackerCtl agentWrapper agentCommunicator agentRegistry pkgs.tmux pkgs.python3 pkgs.coreutils pkgs.procps pkgs.bash ]}:$PATH
              exec ${pkgs.python3}/bin/python3 ${./app/broccoli-comms.py} "$@"
            '';
          };
        in {
          inherit agentTrackerFiles agentTracker agentTrackerCtl agentWrapper agentCommunicator agentCommunicatorElectron agentRegistry managedAgent broccoliComms;
          agent-tracker = agentTracker;
          agent-tracker-ctl = agentTrackerCtl;
          agent-wrapper = agentWrapper;
          agent-communicator = agentCommunicator;
          agent-communicator-electron = agentCommunicatorElectron;
          agent-registry = agentRegistry;
          agent-registry-managed-agent = managedAgent;
          default = broccoliComms;
        });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            go
            gnumake
            nodejs
            python3
            tmux
          ];
        };
      });

      checks = forAllSystems (pkgs: {
        python-syntax = pkgs.runCommand "broccoli-comms-python-syntax" { } ''
          cp -R ${./app} app
          cp -R ${./agent-tracker} agent-tracker
          cp -R ${./agent-registry} agent-registry
          chmod -R u+w app agent-tracker agent-registry
          ${pkgs.python3}/bin/python3 -m py_compile app/broccoli-comms.py agent-tracker/*.py agent-tracker/ctl_commands/*.py agent-registry/*.py
          touch $out
        '';

        tracker-unit = pkgs.runCommand "broccoli-comms-tracker-unit" { } ''
          cp -R ${./agent-tracker} agent-tracker
          chmod -R u+w agent-tracker
          cd agent-tracker
          ${pkgs.python3}/bin/python3 -m unittest test_tmux_util.py test_spin_command.py test_agent_tracker_ctl.py
          touch $out
        '';

        registry-unit = pkgs.runCommand "broccoli-comms-registry-unit" { } ''
          cp -R ${./agent-registry} agent-registry
          chmod -R u+w agent-registry
          cd agent-registry
          ${pkgs.python3}/bin/python3 -m unittest test_managed_agent.py
          touch $out
        '';

        shell-syntax = pkgs.runCommand "broccoli-comms-shell-syntax" { } ''
          ${pkgs.bash}/bin/bash -n ${./wrapper/agent-wrapper.sh}
          ${pkgs.bash}/bin/bash -n ${./scripts/smoke-private-runtime.sh}
          ${pkgs.bash}/bin/bash -n ${./scripts/smoke-managed-agents.sh}
          touch $out
        '';

        communicator-tests = pkgs.buildGoModule {
          pname = "broccoli-comms-communicator-tests";
          version = "0.1.0";
          src = ./agent-communicator-tui;
          vendorHash = null;
          doCheck = true;
          installPhase = ''
            mkdir -p $out
          '';
        };
      });

      apps = forAllSystems (pkgs:
        let system = pkgs.stdenv.hostPlatform.system;
        in {
          default = {
            type = "app";
            program = "${self.packages.${system}.broccoliComms}/bin/broccoli-comms";
            meta.description = "Standalone Broccoli Comms agent runtime";
          };
          broccoli-comms = {
            type = "app";
            program = "${self.packages.${system}.broccoliComms}/bin/broccoli-comms";
            meta.description = "Standalone Broccoli Comms agent runtime";
          };
          agent-communicator-electron = {
            type = "app";
            program = "${self.packages.${system}.agentCommunicatorElectron}/bin/agent-communicator-electron";
            meta.description = "Broccoli Comms Electron desktop app";
          };
        });

      homeManagerModules = {
        broccoli-comms = import ./modules/home-manager.nix self;
        default = self.homeManagerModules.broccoli-comms;
      };

      nixosModules = {
        broccoli-comms = import ./modules/nixos.nix self;
        default = self.nixosModules.broccoli-comms;
      };
    };
}
