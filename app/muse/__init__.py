"""Muse - a local visual board."""

__version__ = "1.0.0"

# The shop hosts a tiny JSON manifest describing the newest release. Muse checks
# it quietly on start and offers (never forces) an update. Point this at wherever
# you upload latest.json on your shop; the manifest's own "url" field points at
# the installer to download. See updater.py for the manifest format.
UPDATE_URL = "https://martinworks.org/muse/latest.json"
