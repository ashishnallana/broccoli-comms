from .common import format_registry_status, load_registry_status


def register(subparsers):
    parser = subparsers.add_parser("registry-status", help="Show per-registry connection status")
    parser.set_defaults(handler=handle)


def handle(_args):
    print(format_registry_status(load_registry_status()))
