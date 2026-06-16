self: { config, lib, pkgs, ... }:
let
  cfg = config.services.broccoli-comms;
  pcfg = config.programs.broccoli-comms;
  packages = self.packages.${pkgs.system};

  registrySpecType = lib.types.submodule {
    options = {
      name = lib.mkOption { type = lib.types.str; description = "Registry name."; };
      url = lib.mkOption { type = lib.types.str; description = "Registry base URL."; };
      token-file = lib.mkOption { type = lib.types.nullOr lib.types.str; default = null; description = "Optional token file."; };
    };
  };

  agentSpecType = lib.types.submodule ({ name, ... }: {
    options = {
      cwd = lib.mkOption { type = lib.types.str; default = "~"; description = "Working directory for managed agent ${name}."; };
      command = lib.mkOption { type = lib.types.str; default = "pi"; description = "Command for managed agent ${name}."; };
      autostart = lib.mkOption { type = lib.types.bool; default = false; description = "Whether broccoli-comms start/ui should launch managed agent ${name}."; };
    };
  });

  userHome =
    if cfg.userHome != null then cfg.userHome
    else if lib.hasAttrByPath [ "users" "users" cfg.user "home" ] config then lib.getAttrFromPath [ "users" "users" cfg.user "home" ] config
    else "/home/${cfg.user}";

  envList = attrs: lib.mapAttrsToList (name: value: "${name}=\"${builtins.replaceStrings ["\""] ["\\\""] (toString value)}\"") attrs;
  optionalEnv = name: value: lib.optionalAttrs (value != null) { ${name} = value; };

  runtimeEnv = {
    AGENT_TRACKER_HOSTNAME = cfg.hostname;
    HOME = userHome;
    USER = cfg.user;
  } // optionalEnv "BROCCOLI_COMMS_RUNTIME_DIR" cfg.runtimeDir
    // optionalEnv "BROCCOLI_COMMS_CACHE_DIR" cfg.cacheDir
    // optionalEnv "BROCCOLI_COMMS_CONFIG_DIR" cfg.configDir
    // lib.optionalAttrs (cfg.registries != []) { AGENT_REGISTRIES_JSON = builtins.toJSON cfg.registries; }
    // lib.optionalAttrs cfg.remotePaneInput.enable { BROCCOLI_COMMS_REMOTE_PANE_INPUT_ENABLED = "1"; };

  configDir = if cfg.configDir != null then cfg.configDir else "${userHome}/.config/broccoli-comms";
  cacheDir = if cfg.cacheDir != null then cfg.cacheDir else "${userHome}/.cache/broccoli-comms";
  runtimeConfig = { agents = lib.mapAttrs (_: spec: { inherit (spec) cwd command autostart; }) cfg.agents; };

  registryStatePath = if cfg.registry.statePath != null then cfg.registry.statePath else "/var/lib/broccoli-comms-registry/state.json";
  registryEnv = {
    AGENT_REGISTRY_PORT = toString cfg.registry.port;
    AGENT_REGISTRY_AUTH = if cfg.registry.auth then "true" else "false";
    TRACKER_STALE_SECONDS = toString cfg.registry.staleSeconds;
    TRACKER_GONE_SECONDS = toString cfg.registry.goneSeconds;
    AGENT_REGISTRY_STATE_PATH = registryStatePath;
  };
  registryStart = pkgs.writeShellScript "broccoli-comms-registry-start" ''
    ${lib.optionalString cfg.registry.auth ''export AGENT_REGISTRY_TOKEN="$(cat "$CREDENTIALS_DIRECTORY/registry-token")"''}
    exec ${cfg.registry.package}/bin/agent-registry
  '';
in {
  options.programs.broccoli-comms = with lib; {
    enable = mkEnableOption "Broccoli Comms packages";
    package = mkOption { type = types.package; default = packages.broccoliComms; defaultText = "self.packages.<system>.broccoliComms"; };
    install = {
      tracker = mkOption { type = types.bool; default = true; };
      trackerCtl = mkOption { type = types.bool; default = true; };
      wrapper = mkOption { type = types.bool; default = true; };
      registry = mkOption { type = types.bool; default = false; };
      managedAgent = mkOption { type = types.bool; default = false; };
      tui = mkOption { type = types.bool; default = true; };
    };
  };

  options.services.broccoli-comms = with lib; {
    enable = mkEnableOption "Broccoli Comms private runtime system service";
    package = mkOption { type = types.package; default = packages.broccoliComms; defaultText = "self.packages.<system>.broccoliComms"; };
    user = mkOption { type = types.str; description = "User that owns the private tmux runtime."; };
    userHome = mkOption { type = types.nullOr types.str; default = null; };
    hostname = mkOption { type = types.str; default = "broccoli-comms"; };
    runtimeDir = mkOption { type = types.nullOr types.str; default = null; };
    cacheDir = mkOption { type = types.nullOr types.str; default = null; };
    configDir = mkOption { type = types.nullOr types.str; default = null; };
    registries = mkOption { type = types.listOf registrySpecType; default = []; };
    agents = mkOption { type = types.attrsOf agentSpecType; default = {}; };
    remotePaneInput.enable = mkOption { type = types.bool; default = false; };

    registry = {
      enable = mkEnableOption "Broccoli Comms registry system service";
      package = mkOption { type = types.package; default = packages.agentRegistry; defaultText = "self.packages.<system>.agentRegistry"; };
      port = mkOption { type = types.port; default = 18000; };
      auth = mkOption { type = types.bool; default = false; };
      tokenFile = mkOption { type = types.nullOr types.path; default = null; };
      staleSeconds = mkOption { type = types.int; default = 60; };
      goneSeconds = mkOption { type = types.int; default = 180; };
      statePath = mkOption { type = types.nullOr types.str; default = null; };
    };
  };

  config = lib.mkMerge [
    (lib.mkIf pcfg.enable {
      environment.systemPackages = [ pcfg.package ]
        ++ lib.optional pcfg.install.tracker packages.agentTracker
        ++ lib.optional pcfg.install.trackerCtl packages.agentTrackerCtl
        ++ lib.optional pcfg.install.wrapper packages.agentWrapper
        ++ lib.optional pcfg.install.registry packages.agentRegistry
        ++ lib.optional pcfg.install.managedAgent packages.managedAgent
        ++ lib.optional pcfg.install.tui packages.agentCommunicator;
    })

    (lib.mkIf cfg.enable {
      programs.broccoli-comms.enable = lib.mkDefault true;
      systemd.tmpfiles.rules = [
        "d ${configDir} 0755 ${cfg.user} users - -"
        "d ${cacheDir} 0755 ${cfg.user} users - -"
      ];
      environment.etc."broccoli-comms/config-${cfg.user}.json".text = builtins.toJSON runtimeConfig;
      systemd.services.broccoli-comms = {
        description = "Broccoli Comms private runtime";
        wantedBy = [ "multi-user.target" ];
        environment = runtimeEnv;
        preStart = ''
          install -d -m 0755 -o ${cfg.user} -g users ${configDir}
          cp /etc/broccoli-comms/config-${cfg.user}.json ${configDir}/config.json
          chown ${cfg.user}:users ${configDir}/config.json
        '';
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = cfg.user;
          WorkingDirectory = userHome;
          ExecStart = "${cfg.package}/bin/broccoli-comms start";
          ExecStop = "${cfg.package}/bin/broccoli-comms stop";
        };
      };
    })

    (lib.mkIf cfg.registry.enable {
      assertions = [{ assertion = !cfg.registry.auth || cfg.registry.tokenFile != null; message = "services.broccoli-comms.registry.tokenFile is required when auth is enabled."; }];
      programs.broccoli-comms.enable = lib.mkDefault true;
      programs.broccoli-comms.install.registry = lib.mkDefault true;
      systemd.services.broccoli-comms-registry = {
        description = "Broccoli Comms agent registry";
        wantedBy = [ "multi-user.target" ];
        environment = registryEnv;
        serviceConfig = {
          StateDirectory = "broccoli-comms-registry";
          LoadCredential = lib.optional cfg.registry.auth "registry-token:${cfg.registry.tokenFile}";
          ExecStart = toString registryStart;
          Restart = "always";
        };
      };
    })
  ];
}
