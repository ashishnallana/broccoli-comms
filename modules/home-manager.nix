self: { config, lib, pkgs, ... }:
let
  cfg = config.services.broccoli-comms;
  pcfg = config.programs.broccoli-comms;
  packages = self.packages.${pkgs.system};

  registrySpecType = lib.types.submodule {
    options = {
      name = lib.mkOption { type = lib.types.str; description = "Registry name."; };
      url = lib.mkOption { type = lib.types.str; description = "Registry base URL."; };
      token-file = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Optional token file for this registry.";
      };
    };
  };

  cacheRoot = config.xdg.cacheHome or "${config.home.homeDirectory}/.cache";
  stateRoot = config.xdg.stateHome or "${config.home.homeDirectory}/.local/state";
  configRoot = config.xdg.configHome or "${config.home.homeDirectory}/.config";

  trackerCacheDir = if cfg.tracker.cacheDir != null then cfg.tracker.cacheDir else "${cacheRoot}/broccoli-comms/agent-tracker";
  trackerSocket = if cfg.tracker.socketPath != null then cfg.tracker.socketPath else "${trackerCacheDir}/agent-tracker.sock";
  trackerStdout = "${trackerCacheDir}/launchd.stdout.log";
  trackerStderr = "${trackerCacheDir}/launchd.stderr.log";
  trackerHostSuffixPath = "${stateRoot}/broccoli-comms/agent-tracker/hostname-suffix";

  envList = attrs: lib.mapAttrsToList (name: value: "${name}=${toString value}") attrs;
  optionalEnv = name: value: lib.optionalAttrs (value != null) { ${name} = value; };

  trackerEnv = {
    AGENT_TRACKER_SOCKET = trackerSocket;
    XDG_CACHE_HOME = builtins.dirOf trackerCacheDir;
    AGENT_TRACKER_HTTP_PORT = toString cfg.tracker.httpPort;
    AGENT_REGISTRY_HEARTBEAT_SECONDS = toString cfg.tracker.registryHeartbeatSeconds;
    AGENT_REGISTRY_AUTH = if cfg.tracker.registryAuth then "true" else "false";
    ENABLE_RELIABLE_SEND_KEYS = if cfg.tracker.enableReliableSendKeys then "true" else "false";
    AGENT_TRACKER_CAPTURE_PANE_DEFAULT_LINES = toString cfg.tracker.capturePaneDefaultLines;
    PATH = lib.concatStringsSep ":" [
      "${config.home.homeDirectory}/.nix-profile/bin"
      "/etc/profiles/per-user/${config.home.username}/bin"
      "/nix/var/nix/profiles/default/bin"
      "/run/current-system/sw/bin"
      "/usr/local/bin"
      "/opt/homebrew/bin"
      "/usr/bin"
      "/bin"
      "/usr/sbin"
      "/sbin"
      (lib.makeBinPath [ pkgs.tmux pkgs.coreutils pkgs.gnugrep pkgs.procps pkgs.bash ])
    ];
  } // optionalEnv "AGENT_TRACKER_HOSTNAME" cfg.tracker.hostname
    // optionalEnv "AGENT_TRACKER_TMUX_SOCKET" cfg.tracker.tmuxSocketPath
    // optionalEnv "AGENT_REGISTRY_TOKEN" cfg.tracker.registryToken
    // lib.optionalAttrs (cfg.tracker.registries != []) {
      AGENT_REGISTRIES_JSON = builtins.toJSON cfg.tracker.registries;
    }
    // lib.optionalAttrs cfg.tracker.remotePaneInput.enable {
      BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED = "1";
    }
    // cfg.tracker.environment;

  trackerStart = pkgs.writeShellScript "broccoli-comms-agent-tracker-start" ''
    if [ -z "''${AGENT_TRACKER_HOSTNAME:-}" ]; then
      suffix_file=${lib.escapeShellArg trackerHostSuffixPath}
      mkdir -p "$(dirname "$suffix_file")"
      if [ ! -s "$suffix_file" ]; then
        ${pkgs.python3}/bin/python3 - <<'PY' > "$suffix_file"
import random
import string
print(''.join(random.choice(string.ascii_lowercase) for _ in range(3)))
PY
      fi
      suffix="$(tr -cd 'a-z' < "$suffix_file" | cut -c1-3)"
      if [ "''${#suffix}" -ne 3 ]; then
        suffix="$(${pkgs.python3}/bin/python3 - <<'PY'
import random
import string
print(''.join(random.choice(string.ascii_lowercase) for _ in range(3)))
PY
)"
        printf '%s\n' "$suffix" > "$suffix_file"
      fi
      base="$(hostname -s 2>/dev/null || hostname 2>/dev/null || printf '%s' ${lib.escapeShellArg config.home.username})"
      base="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '-' | sed 's/^-//; s/-$//')"
      export AGENT_TRACKER_HOSTNAME="''${base:-${config.home.username}}-$suffix"
    fi
    ${lib.optionalString (cfg.tracker.registryAuth && cfg.tracker.registryTokenFile != null) ''export AGENT_REGISTRY_TOKEN="$(cat ${lib.escapeShellArg (toString cfg.tracker.registryTokenFile)})"''}
    exec ${cfg.tracker.package}/bin/agent-tracker
  '';

  registryStatePath = if cfg.registry.statePath != null then cfg.registry.statePath else "${stateRoot}/broccoli-comms/agent-registry/state.json";
  registryCacheDir = if cfg.registry.cacheDir != null then cfg.registry.cacheDir else "${cacheRoot}/broccoli-comms/agent-registry";
  registryEnv = {
    AGENT_REGISTRY_HOST = cfg.registry.host;
    AGENT_REGISTRY_PORT = toString cfg.registry.port;
    AGENT_REGISTRY_AUTH = if cfg.registry.auth then "true" else "false";
    TRACKER_STALE_SECONDS = toString cfg.registry.staleSeconds;
    TRACKER_GONE_SECONDS = toString cfg.registry.goneSeconds;
    AGENT_REGISTRY_STATE_PATH = registryStatePath;
  } // cfg.registry.environment;
  registryStart = pkgs.writeShellScript "broccoli-comms-agent-registry-start" ''
    ${lib.optionalString cfg.registry.auth ''export AGENT_REGISTRY_TOKEN="$(cat ${lib.escapeShellArg (toString cfg.registry.tokenFile)})"''}
    exec ${cfg.registry.package}/bin/agent-registry
  '';

  electronEnv = {
    AGENT_TRACKER_SOCKET = trackerSocket;
  } // optionalEnv "AGENT_TRACKER_HOSTNAME" cfg.tracker.hostname
    // cfg.electron.environment;
  electronStart = pkgs.writeShellScript "broccoli-comms-electron-start" ''
    exec ${cfg.electron.package}/bin/agent-communicator-electron
  '';

  installedPackages =
    lib.optionals pcfg.enable ([ pcfg.package ]
      ++ lib.optional pcfg.install.tracker packages.agentTracker
      ++ lib.optional pcfg.install.trackerCtl packages.agentTrackerCtl
      ++ lib.optional pcfg.install.wrapper packages.agentWrapper
      ++ lib.optional pcfg.install.registry packages.agentRegistry
      ++ lib.optional pcfg.install.managedAgent packages.managedAgent
      ++ lib.optional pcfg.install.tui packages.agentCommunicator
      ++ lib.optional pcfg.install.electron packages.agentCommunicatorElectron);
in {
  options.programs.broccoli-comms = with lib; {
    enable = mkEnableOption "Broccoli Comms command-line tools";
    package = mkOption {
      type = types.package;
      default = packages.broccoliComms;
      defaultText = "self.packages.<system>.broccoliComms";
      description = "Main broccoli-comms CLI package.";
    };
    install = {
      tracker = mkOption { type = types.bool; default = true; description = "Install agent-tracker."; };
      trackerCtl = mkOption { type = types.bool; default = true; description = "Install agent-tracker-ctl."; };
      wrapper = mkOption { type = types.bool; default = true; description = "Install agent-wrapper."; };
      registry = mkOption { type = types.bool; default = false; description = "Install agent-registry."; };
      managedAgent = mkOption { type = types.bool; default = false; description = "Install agent-registry-managed-agent."; };
      tui = mkOption { type = types.bool; default = true; description = "Install agent-communicator TUI."; };
      electron = mkOption { type = types.bool; default = false; description = "Install Electron launcher."; };
    };
  };

  options.services.broccoli-comms = with lib; {
    enable = mkEnableOption "Broccoli Comms agent-tracker service";

    tracker = {
      enable = mkOption { type = types.bool; default = cfg.enable; description = "Enable agent-tracker as a systemd user service or launchd agent."; };
      package = mkOption { type = types.package; default = packages.agentTracker; defaultText = "self.packages.<system>.agentTracker"; };
      hostname = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Optional AGENT_TRACKER_HOSTNAME override. When null, the service generates a stable <machine-hostname>-<three-letter-suffix> identity and stores the suffix under XDG state.";
      };
      socketPath = mkOption { type = types.nullOr types.str; default = null; description = "AGENT_TRACKER_SOCKET. Defaults to ~/.cache/broccoli-comms/agent-tracker/agent-tracker.sock."; };
      cacheDir = mkOption { type = types.nullOr types.str; default = null; description = "Tracker cache directory. Defaults to ~/.cache/broccoli-comms/agent-tracker."; };
      tmuxSocketPath = mkOption { type = types.nullOr types.str; default = null; description = "Optional AGENT_TRACKER_TMUX_SOCKET."; };
      httpPort = mkOption { type = types.port; default = 19876; };
      registries = mkOption { type = types.listOf registrySpecType; default = []; description = "Registries published to AGENT_REGISTRIES_JSON."; };
      registryAuth = mkOption { type = types.bool; default = false; };
      registryTokenFile = mkOption { type = types.nullOr types.path; default = null; };
      registryToken = mkOption { type = types.nullOr types.str; default = null; description = "Inline registry token. Prefer registryTokenFile for secrets."; };
      registryHeartbeatSeconds = mkOption { type = types.ints.positive; default = 30; };
      enableReliableSendKeys = mkOption { type = types.bool; default = true; };
      capturePaneDefaultLines = mkOption { type = types.ints.positive; default = 25; };
      remotePaneInput.enable = mkOption { type = types.bool; default = false; };
      environment = mkOption { type = types.attrsOf types.str; default = {}; description = "Extra environment for the tracker service."; };
    };

    registry = {
      enable = mkEnableOption "Broccoli Comms agent-registry service";
      package = mkOption { type = types.package; default = packages.agentRegistry; defaultText = "self.packages.<system>.agentRegistry"; };
      host = mkOption { type = types.str; default = "127.0.0.1"; description = "Bind host for agent-registry."; };
      port = mkOption { type = types.port; default = 18000; };
      auth = mkOption { type = types.bool; default = false; };
      tokenFile = mkOption { type = types.nullOr types.path; default = null; };
      staleSeconds = mkOption { type = types.int; default = 60; };
      goneSeconds = mkOption { type = types.int; default = 180; };
      statePath = mkOption { type = types.nullOr types.str; default = null; };
      cacheDir = mkOption { type = types.nullOr types.str; default = null; };
      environment = mkOption { type = types.attrsOf types.str; default = {}; };
    };

    electron = {
      enable = mkEnableOption "Broccoli Comms Electron desktop app service";
      package = mkOption { type = types.package; default = packages.agentCommunicatorElectron; defaultText = "self.packages.<system>.agentCommunicatorElectron"; };
      environment = mkOption { type = types.attrsOf types.str; default = {}; description = "Extra environment for Electron."; };
    };
  };

  config = lib.mkMerge [
    (lib.mkIf (cfg.tracker.enable || cfg.registry.enable || cfg.electron.enable) {
      programs.broccoli-comms.enable = lib.mkDefault true;
    })

    (lib.mkIf pcfg.enable {
      home.packages = installedPackages;
    })

    (lib.mkIf cfg.tracker.enable {
      assertions = [{ assertion = !cfg.tracker.registryAuth || cfg.tracker.registryTokenFile != null || cfg.tracker.registryToken != null; message = "services.broccoli-comms.tracker.registryTokenFile or registryToken is required when registryAuth is enabled."; }];
      home.activation.ensureBroccoliCommsTrackerDirs = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        mkdir -p ${lib.escapeShellArg trackerCacheDir}
      '';
    })

    (lib.mkIf (cfg.tracker.enable && pkgs.stdenv.isLinux) {
      systemd.user.services.broccoli-comms-agent-tracker = {
        Unit.Description = "Broccoli Comms agent-tracker daemon";
        Service = {
          Environment = envList trackerEnv;
          ExecStart = toString trackerStart;
          Restart = "always";
          RestartSec = 2;
        };
        Install.WantedBy = [ "default.target" ];
      };
    })

    (lib.mkIf (cfg.tracker.enable && pkgs.stdenv.isDarwin) {
      launchd.agents.broccoli-comms-agent-tracker = {
        enable = true;
        config = {
          ProgramArguments = [ (toString trackerStart) ];
          EnvironmentVariables = trackerEnv;
          KeepAlive = false;
          RunAtLoad = true;
          ProcessType = "Background";
          StandardOutPath = trackerStdout;
          StandardErrorPath = trackerStderr;
        };
      };
    })

    (lib.mkIf cfg.registry.enable {
      assertions = [{ assertion = !cfg.registry.auth || cfg.registry.tokenFile != null; message = "services.broccoli-comms.registry.tokenFile is required when auth is enabled."; }];
      programs.broccoli-comms.install.registry = lib.mkDefault true;
      home.activation.ensureBroccoliCommsRegistryDirs = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
        mkdir -p ${lib.escapeShellArg (builtins.dirOf registryStatePath)} ${lib.escapeShellArg registryCacheDir}
      '';
    })

    (lib.mkIf (cfg.registry.enable && pkgs.stdenv.isLinux) {
      systemd.user.services.broccoli-comms-agent-registry = {
        Unit.Description = "Broccoli Comms agent-registry";
        Service = {
          Environment = envList registryEnv;
          ExecStart = toString registryStart;
          Restart = "always";
        };
        Install.WantedBy = [ "default.target" ];
      };
    })

    (lib.mkIf (cfg.registry.enable && pkgs.stdenv.isDarwin) {
      launchd.agents.broccoli-comms-agent-registry = {
        enable = true;
        config = {
          ProgramArguments = [ (toString registryStart) ];
          EnvironmentVariables = registryEnv;
          KeepAlive = true;
          RunAtLoad = true;
          ProcessType = "Background";
          StandardOutPath = "${registryCacheDir}/launchd.stdout.log";
          StandardErrorPath = "${registryCacheDir}/launchd.stderr.log";
        };
      };
    })

    (lib.mkIf cfg.electron.enable {
      programs.broccoli-comms.install.electron = lib.mkDefault true;
    })

    (lib.mkIf (cfg.electron.enable && pkgs.stdenv.isLinux) {
      systemd.user.services.broccoli-comms-electron = {
        Unit.Description = "Broccoli Comms Electron app";
        Service = {
          Environment = envList electronEnv;
          ExecStart = toString electronStart;
          Restart = "on-failure";
        };
        Install.WantedBy = [ "default.target" ];
      };
    })

    (lib.mkIf (cfg.electron.enable && pkgs.stdenv.isDarwin) {
      launchd.agents.broccoli-comms-electron = {
        enable = true;
        config = {
          ProgramArguments = [ (toString electronStart) ];
          EnvironmentVariables = electronEnv;
          RunAtLoad = true;
          ProcessType = "Interactive";
          StandardOutPath = "${trackerCacheDir}/electron.stdout.log";
          StandardErrorPath = "${trackerCacheDir}/electron.stderr.log";
        };
      };
    })
  ];
}
