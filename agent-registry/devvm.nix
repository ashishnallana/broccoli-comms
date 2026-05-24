{ self, pkgs, ... }:
{
  imports = [ self.nixosModules.default ];

  networking.hostName = "agent-registry-devvm";
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = true;
      PermitRootLogin = "yes";
    };
  };

  users.users.dev = {
    isNormalUser = true;
    initialPassword = "dev";
    extraGroups = [ "wheel" ];
    createHome = true;
    home = "/home/dev";
    packages = [ pkgs.tmux pkgs.git pkgs.curl pkgs.jq ];
  };
  users.users.root.initialPassword = "root";

  security.sudo.wheelNeedsPassword = false;

  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    trusted-users = [ "root" "dev" ];
  };

  environment.systemPackages = [
    pkgs.tmux
    pkgs.git
    pkgs.curl
    pkgs.jq
    self.packages.${pkgs.system}.default
  ];

  services.agent-registry = {
    enable = true;
    auth = false;
  };

  fileSystems."/" = {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
    autoResize = true;
  };

  boot.loader.grub = {
    enable = true;
    device = "/dev/vda";
  };

  virtualisation.vmVariant = {
    virtualisation = {
      graphics = false;
      memorySize = 2048;
      cores = 2;
      forwardPorts = [
        { from = "host"; host.port = 2222; guest.port = 22; }
        { from = "host"; host.port = 8080; guest.port = 8080; }
      ];
    };
  };

  system.stateVersion = "24.05";
}
