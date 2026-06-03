self: { config, lib, pkgs, ... }:
let
  cfg = config.services.agent-registry;
  homeDir = config.home.homeDirectory;
  cacheHome = config.xdg.cacheHome or "${homeDir}/.cache";
  stateHome = config.xdg.stateHome or "${homeDir}/.local/state";
  managedAgents = lib.filterAttrs (_: spec: spec.enable) cfg.managedAgents;

  managedUnitName = prefix: agentName: "agent-registry-${prefix}-${lib.replaceStrings [ "/" " " ] [ "-" "-" ] agentName}";

  userPath = lib.concatStringsSep ":" [
    "${homeDir}/.nix-profile/bin"
    "/etc/profiles/per-user/${config.home.username}/bin"
    "/nix/var/nix/profiles/default/bin"
    "/run/current-system/sw/bin"
    (lib.makeBinPath [ pkgs.tmux pkgs.coreutils pkgs.procps pkgs.bash ])
  ];

  trackerSocketFor = spec:
    if spec.trackerSocketPath != null then spec.trackerSocketPath else "${cacheHome}/broccoli-comms/runtime/agent-tracker.sock";

  tmuxSocketFor = spec: spec.tmuxSocketPath;

  baseEnvironmentFor = spec: {
    HOME = homeDir;
    USER = config.home.username;
    PATH = lib.mkForce userPath;
    AGENT_TRACKER_SOCKET = trackerSocketFor spec;
  } // lib.optionalAttrs (tmuxSocketFor spec != null) {
    AGENT_REGISTRY_TMUX_SOCKET = tmuxSocketFor spec;
  };

  launcherArgsFor = agentName: spec:
    ''--agent-name ${lib.escapeShellArg agentName} --session ${lib.escapeShellArg spec.session} --cwd ${lib.escapeShellArg spec.cwd} --command ${lib.escapeShellArg spec.command} --home ${lib.escapeShellArg homeDir} --tracker-socket ${lib.escapeShellArg (trackerSocketFor spec)}${lib.optionalString (tmuxSocketFor spec != null) " --tmux-socket ${lib.escapeShellArg (tmuxSocketFor spec)}"} --wrapper-path ${lib.escapeShellArg spec.wrapperPath}'';

  mkManagedService = agentName: spec:
    let unitName = managedUnitName "managed" agentName; in
    lib.nameValuePair unitName {
      Unit.Description = "Reconcile managed agent ${agentName} for agent-registry";
      Service = {
        Type = "oneshot";
        Environment = lib.mapAttrsToList (name: value: "${name}=${value}") (baseEnvironmentFor spec);
        WorkingDirectory = homeDir;
        TimeoutStartSec = "120s";
        ExecStart = ''${self.packages.${pkgs.system}.default}/bin/agent-registry-managed-agent ${launcherArgsFor agentName spec}'';
      };
      Install.WantedBy = [ "default.target" ];
    };

  mkManagedTimer = agentName: spec:
    let unitName = managedUnitName "managed" agentName; in
    lib.nameValuePair unitName {
      Unit.Description = "Timer for managed agent ${agentName} reconcile";
      Timer = {
        OnBootSec = "15s";
        OnUnitActiveSec = "${toString spec.reconcileIntervalSeconds}s";
        Persistent = true;
        Unit = "${unitName}.service";
      };
      Install.WantedBy = [ "timers.target" ];
    };

  restartEnabledAgents = lib.filterAttrs (_: spec: spec.restart.enable) managedAgents;

  mkRestartService = agentName: spec:
    let
      unitName = managedUnitName "restart" agentName;
      warningMessage = spec.restart.warningMessage or "";
    in lib.nameValuePair unitName {
      Unit.Description = "Scheduled restart for managed agent ${agentName}";
      Service = {
        Type = "oneshot";
        Environment = lib.mapAttrsToList (name: value: "${name}=${value}") (baseEnvironmentFor spec);
        WorkingDirectory = homeDir;
        TimeoutStartSec = "${toString (spec.restart.warningLeadTimeSeconds + 120)}s";
        ExecStart = ''${self.packages.${pkgs.system}.default}/bin/agent-registry-managed-agent ${launcherArgsFor agentName spec} --restart --warning-lead-time-seconds ${toString spec.restart.warningLeadTimeSeconds}${lib.optionalString (warningMessage != "") " --warning-message ${lib.escapeShellArg warningMessage}"}'';
      };
      Install.WantedBy = [ "default.target" ];
    };

  mkRestartTimer = agentName: spec:
    let unitName = managedUnitName "restart" agentName; in
    lib.nameValuePair unitName {
      Unit.Description = "Timer for managed agent ${agentName} restart";
      Timer = {
        Persistent = true;
        Unit = "${unitName}.service";
      } // lib.optionalAttrs (spec.restart.onCalendar != null) {
        OnCalendar = spec.restart.onCalendar;
      } // lib.optionalAttrs (spec.restart.intervalSeconds != null) {
        OnBootSec = "15s";
        OnUnitActiveSec = "${toString spec.restart.intervalSeconds}s";
      };
      Install.WantedBy = [ "timers.target" ];
    };

  restartAssertions = lib.mapAttrsToList (agentName: spec: {
    assertion = (!spec.restart.enable) || (spec.restart.onCalendar != null || spec.restart.intervalSeconds != null);
    message = "services.agent-registry.managedAgents.${agentName}.restart requires onCalendar or intervalSeconds when enabled.";
  }) managedAgents;

  envFile = pkgs.writeText "agent-registry-user.env" ''
    AGENT_REGISTRY_PORT=${toString cfg.port}
    AGENT_REGISTRY_AUTH=${if cfg.auth then "true" else "false"}
    TRACKER_STALE_SECONDS=${toString cfg.staleSeconds}
    TRACKER_GONE_SECONDS=${toString cfg.goneSeconds}
    AGENT_REGISTRY_STATE_PATH=${stateHome}/agent-registry/state.json
  '';

  startScript = pkgs.writeShellScript "agent-registry-user-start" ''
    ${lib.optionalString cfg.auth ''export AGENT_REGISTRY_TOKEN="$(cat ${lib.escapeShellArg (toString cfg.tokenFile)})"''}
    exec ${self.packages.${pkgs.system}.default}/bin/agent-registry
  '';
in {
  options.services.agent-registry = with lib; {
    enable = mkEnableOption "agent-registry user service";
    port = mkOption { type = types.port; default = 8080; };
    auth = mkOption { type = types.bool; default = true; };
    tokenFile = mkOption {
      type = types.nullOr types.path;
      default = null;
      description = "User-readable file containing the shared Bearer token for registry auth.";
    };
    staleSeconds = mkOption { type = types.int; default = 60; };
    goneSeconds = mkOption { type = types.int; default = 180; };
    managedAgents = mkOption {
      default = {};
      type = types.attrsOf (types.submodule ({ name, ... }: {
        options = {
          enable = mkEnableOption "managed agent ${name}" // { default = true; };
          session = mkOption {
            type = types.str;
            default = name;
            description = "Tmux session name that should contain this managed agent.";
          };
          cwd = mkOption {
            type = types.str;
            default = homeDir;
            description = "Working directory to use when starting the managed agent.";
          };
          command = mkOption {
            type = types.str;
            description = "Command to run via the configured wrapper, for example `pi` or `claude`.";
          };
          wrapperPath = mkOption {
            type = types.str;
            default = "agent-wrapper";
            description = "Wrapper executable used to launch the agent. Can be a bare command in PATH or an absolute store path.";
          };
          trackerSocketPath = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Optional AGENT_TRACKER_SOCKET override. Defaults to ~/.cache/broccoli-comms/runtime/agent-tracker.sock for the Home Manager user.";
          };
          tmuxSocketPath = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Optional explicit tmux socket path. By default managed agents use the user's normal tmux socket under XDG_RUNTIME_DIR (for example /run/user/<uid>/tmux-<uid>/default). Set this explicitly if you want a dedicated tmux server instead.";
          };
          reconcileIntervalSeconds = mkOption {
            type = types.ints.positive;
            default = 30;
            description = "How often to reconcile the agent into the tmux session.";
          };
          restart = {
            enable = mkOption {
              type = types.bool;
              default = false;
              description = "Whether to schedule periodic restarts for this agent.";
            };
            onCalendar = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Optional systemd OnCalendar expression for scheduled restarts.";
            };
            intervalSeconds = mkOption {
              type = types.nullOr types.ints.positive;
              default = null;
              description = "Optional systemd OnUnitActiveSec interval for scheduled restarts.";
            };
            warningLeadTimeSeconds = mkOption {
              type = types.addCheck types.int (x: x >= 0);
              default = 300;
              description = "How long to wait after sending an in-band restart warning before restarting the pane.";
            };
            warningMessage = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Optional custom warning message sent to the pane before a scheduled restart.";
            };
          };
        };
      }));
      description = ''
        User-scoped managed agents to keep running inside tmux. Reconciliation and
        scheduled restarts run as the Home Manager user with explicit HOME/PATH and
        tracker/tmux socket environment.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = pkgs.stdenv.isLinux;
        message = "services.agent-registry Home Manager support currently targets Linux only.";
      }
      {
        assertion = !cfg.auth || cfg.tokenFile != null;
        message = "services.agent-registry.tokenFile is required when auth is enabled.";
      }
    ] ++ restartAssertions;

    home.activation.ensureAgentRegistryDirs = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      mkdir -p ${lib.escapeShellArg "${stateHome}/agent-registry"}
      mkdir -p ${lib.escapeShellArg "${cacheHome}/agent-registry"}
    '';

    systemd.user.services = {
      agent-registry = {
        Unit = {
          Description = "Agent Registry";
        };
        Service = {
          EnvironmentFile = envFile;
          ExecStart = toString startScript;
          Restart = "always";
        };
        Install = {
          WantedBy = [ "default.target" ];
        };
      };
    } // lib.mapAttrs' mkManagedService managedAgents
      // lib.mapAttrs' mkRestartService restartEnabledAgents;

    systemd.user.timers = lib.mapAttrs' mkManagedTimer managedAgents
      // lib.mapAttrs' mkRestartTimer restartEnabledAgents;
  };
}
