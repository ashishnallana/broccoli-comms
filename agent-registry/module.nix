self: { config, lib, pkgs, ... }:
let
  cfg = config.services.agent-registry;
  managedAgents = lib.filterAttrs (_: spec: spec.enable) cfg.managedAgents;

  userHomeFor = spec:
    if spec.home != null then spec.home
    else if lib.hasAttrByPath [ "users" "users" spec.user "home" ] config then lib.getAttrFromPath [ "users" "users" spec.user "home" ] config
    else "/home/${spec.user}";

  userUidFor = spec:
    if lib.hasAttrByPath [ "users" "users" spec.user "uid" ] config then toString (lib.getAttrFromPath [ "users" "users" spec.user "uid" ] config)
    else null;

  managedUnitName = prefix: agentName: "agent-registry-${prefix}-${lib.replaceStrings [ "/" " " ] [ "-" "-" ] agentName}";

  userPathFor = spec:
    let home = userHomeFor spec; in
    lib.concatStringsSep ":" [
      "${home}/.nix-profile/bin"
      "/etc/profiles/per-user/${spec.user}/bin"
      "/nix/var/nix/profiles/default/bin"
      "/run/current-system/sw/bin"
      (lib.makeBinPath [ pkgs.tmux pkgs.coreutils pkgs.procps pkgs.bash ])
    ];

  trackerSocketFor = spec:
    if spec.trackerSocketPath != null then spec.trackerSocketPath else "${userHomeFor spec}/.cache/broccoli-comms/runtime/agent-tracker.sock";

  tmuxSocketFor = spec: spec.tmuxSocketPath;

  baseEnvironmentFor = spec:
    let uid = userUidFor spec; in {
      HOME = userHomeFor spec;
      USER = spec.user;
      PATH = lib.mkForce (userPathFor spec);
      AGENT_TRACKER_SOCKET = trackerSocketFor spec;
    } // lib.optionalAttrs (tmuxSocketFor spec != null) {
      AGENT_REGISTRY_TMUX_SOCKET = tmuxSocketFor spec;
    } // lib.optionalAttrs (uid != null) {
      XDG_RUNTIME_DIR = "/run/user/${uid}";
    };

  launcherArgsFor = agentName: spec:
    ''--agent-name ${lib.escapeShellArg agentName} --session ${lib.escapeShellArg spec.session} --cwd ${lib.escapeShellArg spec.cwd} --command ${lib.escapeShellArg spec.command} --home ${lib.escapeShellArg (userHomeFor spec)} --tracker-socket ${lib.escapeShellArg (trackerSocketFor spec)}${lib.optionalString (tmuxSocketFor spec != null) " --tmux-socket ${lib.escapeShellArg (tmuxSocketFor spec)}"} --wrapper-path ${lib.escapeShellArg spec.wrapperPath}'';

  mkManagedService = agentName: spec:
    let
      unitName = managedUnitName "managed" agentName;
      home = userHomeFor spec;
    in lib.nameValuePair unitName {
      description = "Reconcile managed agent ${agentName} for agent-registry";
      wantedBy = [ "multi-user.target" ];
      environment = baseEnvironmentFor spec;
      serviceConfig = {
        Type = "oneshot";
        User = spec.user;
        WorkingDirectory = home;
        TimeoutStartSec = "120s";
        KillMode = "none";
        ExecStart = ''${self.packages.${pkgs.system}.default}/bin/agent-registry-managed-agent ${launcherArgsFor agentName spec}'';
      };
    };

  mkManagedTimer = agentName: spec:
    let unitName = managedUnitName "managed" agentName; in
    lib.nameValuePair unitName {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "15s";
        OnUnitActiveSec = "${toString spec.reconcileIntervalSeconds}s";
        Persistent = true;
        Unit = "${unitName}.service";
      };
    };

  restartEnabledAgents = lib.filterAttrs (_: spec: spec.restart.enable) managedAgents;

  mkRestartService = agentName: spec:
    let
      unitName = managedUnitName "restart" agentName;
      home = userHomeFor spec;
      warningMessage = spec.restart.warningMessage or "";
    in lib.nameValuePair unitName {
      description = "Scheduled restart for managed agent ${agentName}";
      environment = baseEnvironmentFor spec;
      serviceConfig = {
        Type = "oneshot";
        User = spec.user;
        WorkingDirectory = home;
        TimeoutStartSec = "${toString (spec.restart.warningLeadTimeSeconds + 120)}s";
        KillMode = "none";
        ExecStart = ''${self.packages.${pkgs.system}.default}/bin/agent-registry-managed-agent ${launcherArgsFor agentName spec} --restart --warning-lead-time-seconds ${toString spec.restart.warningLeadTimeSeconds}${lib.optionalString (warningMessage != "") " --warning-message ${lib.escapeShellArg warningMessage}"}'';
      };
    };

  mkRestartTimer = agentName: spec:
    let unitName = managedUnitName "restart" agentName; in
    lib.nameValuePair unitName {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        Persistent = true;
        Unit = "${unitName}.service";
      } // lib.optionalAttrs (spec.restart.onCalendar != null) {
        OnCalendar = spec.restart.onCalendar;
      } // lib.optionalAttrs (spec.restart.intervalSeconds != null) {
        OnBootSec = "15s";
        OnUnitActiveSec = "${toString spec.restart.intervalSeconds}s";
      };
    };

  restartAssertions = lib.mapAttrsToList (agentName: spec: {
    assertion = (!spec.restart.enable) || (spec.restart.onCalendar != null || spec.restart.intervalSeconds != null);
    message = "services.agent-registry.managedAgents.${agentName}.restart requires onCalendar or intervalSeconds when enabled.";
  }) managedAgents;
in {
  options.services.agent-registry = with lib; {
    enable = mkEnableOption "agent-registry";
    port = mkOption { type = types.port; default = 8080; };
    auth = mkOption { type = types.bool; default = true; };
    tokenFile = mkOption { type = types.nullOr types.path; default = null; };
    staleSeconds = mkOption { type = types.int; default = 60; };
    goneSeconds = mkOption { type = types.int; default = 180; };
    managedAgents = mkOption {
      default = {};
      type = types.attrsOf (types.submodule ({ name, ... }: {
        options = {
          enable = mkEnableOption "managed agent ${name}" // { default = true; };
          user = mkOption {
            type = types.str;
            description = "User that owns the tmux session and runs the agent reconcile command.";
          };
          home = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Override home directory for the target user. Defaults to users.users.<name>.home or /home/<user>.";
          };
          session = mkOption {
            type = types.str;
            description = "Tmux session name that should contain this managed agent.";
          };
          cwd = mkOption {
            type = types.str;
            default = "~";
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
            description = "Optional AGENT_TRACKER_SOCKET override. Defaults to ~/.cache/broccoli-comms/runtime/agent-tracker.sock for the target user.";
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
        Registry-host-local agents to keep running inside tmux. These are keyed by
        logical agent name. Reconciliation and scheduled restarts run as the target
        user with explicit HOME/PATH/XDG_RUNTIME_DIR/AGENT_TRACKER_SOCKET.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [{
      assertion = !cfg.auth || cfg.tokenFile != null;
      message = "services.agent-registry.tokenFile is required when auth is enabled.";
    }] ++ restartAssertions;

    systemd.services = {
      agent-registry = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          StateDirectory = "agent-registry";
          EnvironmentFile = pkgs.writeText "agent-registry.env" ''
            AGENT_REGISTRY_PORT=${toString cfg.port}
            AGENT_REGISTRY_AUTH=${if cfg.auth then "true" else "false"}
            TRACKER_STALE_SECONDS=${toString cfg.staleSeconds}
            TRACKER_GONE_SECONDS=${toString cfg.goneSeconds}
            AGENT_REGISTRY_STATE_PATH=/var/lib/agent-registry/state.json
          '';
          LoadCredential = lib.optional cfg.auth "registry-token:${cfg.tokenFile}";
          ExecStart = toString (pkgs.writeShellScript "agent-registry-start" ''
            ${lib.optionalString cfg.auth ''export AGENT_REGISTRY_TOKEN="$(cat "$CREDENTIALS_DIRECTORY/registry-token")"''}
            exec ${self.packages.${pkgs.system}.default}/bin/agent-registry
          '');
          Restart = "always";
        };
      };
    } // lib.mapAttrs' mkManagedService managedAgents
      // lib.mapAttrs' mkRestartService restartEnabledAgents;

    systemd.timers = lib.mapAttrs' mkManagedTimer managedAgents
      // lib.mapAttrs' mkRestartTimer restartEnabledAgents;
  };
}
