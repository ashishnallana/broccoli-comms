{
  description = "agent-communicator TUI";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system (import nixpkgs { inherit system; }));
    in {
      packages = forAllSystems (system: pkgs: {
        default = pkgs.buildGoModule {
          pname = "agent-communicator";
          version = "0.1.0";
          src = ./.;
          vendorHash = "sha256-TUbaUoqDZoQTkcOMtoE/FlAiqkWN+x49JeGkDguh2UU=";
          ldflags = [ "-X main.version=0.1.0" ];
        };
      });

      apps = forAllSystems (system: pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/agent-communicator-tui";
        };
      });

      checks = forAllSystems (system: pkgs: {
        default = self.packages.${system}.default;
      });

      devShells = forAllSystems (system: pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.go pkgs.gopls pkgs.gotools ];
        };
      });
    };
}
