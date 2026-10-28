import argparse
import logging
import os
import signal
import sys

from src.core.config import Config, TargetPlatform
from src.core.navigator import ScreenNavigator
from src.core.state import ScreenState
from src.utils.data.equipment import EquipmentProcessor
from src.utils.data.item import ItemProcessor
from src.utils.data.student import StudentProcessor
from src.utils.device.factory import create_device
from src.utils.device.interfaces import DeviceController, DeviceUnavailableError
from src.utils.sync.data_sync_manager import DataSyncManager

logger = logging.getLogger("BA-Scanner")


def run_post_processing(scanned_screens: set[str]):
    """
    Only runs processors if the corresponding screen
    was actually successfully scanned.
    """
    processor_map = {
        "Equipment": EquipmentProcessor,
        "Items": ItemProcessor,
        "Student": StudentProcessor,  # The detail pages write scanned_students.json
    }

    for screen_name, ProcessorClass in processor_map.items():
        if screen_name in scanned_screens:
            try:
                logger.info(f"Post-processing {screen_name} data...")
                ProcessorClass().process()
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed to process {screen_name}: {e}")


def post_process_finished(scanned_screens: set[str]):
    """run_post_processing that a second Ctrl+C/F2 can't cut short halfway."""
    stops = [signal.SIGINT] + ([signal.SIGBREAK] if hasattr(signal, "SIGBREAK") else [])
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in stops}
    try:
        run_post_processing(scanned_screens)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    # "python main.py > log.txt" writes in the ANSI code page, which has no ✔ or ▶
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    # launch.py stops a scan with CTRL_BREAK_EVENT (F2): treat it like a Ctrl+C,
    # so the screens finished so far are still post-processed
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline", action="store_true", help="Skip data sync and any network calls"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode for this run."
    )
    args = parser.parse_args()

    if Config.settings_error:
        print(
            "Can't use the settings, fix or delete the file, "
            "then run python launch.py or python -m gui.run:"
        )
        print(Config.settings_error)
        sys.exit(1)
    settings = Config.settings
    if not (Config.CONFIG_DIR / "settings.json").exists():
        print(
            "Warning: config/settings.json not found, using the defaults. "
            "Run python launch.py or python -m gui.run to set up the scan."
        )
    if settings.target_platform == TargetPlatform.DESKTOP:
        print(f"Platform: PC client, window '{settings.window_title}'")
    else:
        print(
            f"Platform: {settings.target_platform.value} over ADB "
            f"{settings.adb_host}:{settings.adb_port}"
        )

    if args.debug:
        Config.DEBUG = True  # Before ScreenState sets the log level from it

    # ponytail: templates, screen_config.json and rapidocr/config.yaml (with its
    # model paths) are relative to the project root, so run from there
    os.chdir(Config.PROJECT_ROOT)
    Config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sync Data
    # Sync if CLI is NOT offline AND settings say Enable Sync is True
    if not args.offline and Config.settings.enable_sync:
        try:
            DataSyncManager().update_from_online()
        except Exception:  # noqa: BLE001, S110
            pass

    # Create device controller based on platform
    device = create_device(Config.settings)

    if not device.connect(Config.ADB_RETRIES):
        logger.error("❌ Failed to connect to the device.")
        sys.exit(1)

    mainpage(device)


def mainpage(device: DeviceController):
    """
    Handles navigation and starts the matching process.
    Logic:
      - If the current screen is None (meaning we're either on Home or on a Page),
        if we're on a Page then a. go Home if that certain screen is finished, b. start immediately.
      - Then loop through each screen defined.
      - Skip already visited screens.
      - If not on the target screen, navigate to it.
        For "Students" and "Student", these are accessed without using the Menu Tab.
      - If navigation is successful, call the matching process (or get info).
    """
    navigator = ScreenNavigator(device)
    state = ScreenState(navigator)

    try:
        finished = state.run()
    except KeyboardInterrupt:  # Ctrl+C, or F2 in launch.py
        logger.warning("Scan stopped by user.")
        post_process_finished(state.scanned)  # Screens finished before the stop
        sys.exit(130)  # The usual exit code after a Ctrl+C
    except DeviceUnavailableError as e:
        logger.error(f"❌ Scan stopped: {e}")
        finished = False
    except Exception:  # noqa: BLE001
        logger.exception("❌ Scan crashed")
        finished = False

    if not finished:
        logger.warning("⚠️ Matching process failed or was interrupted.")
    post_process_finished(state.scanned)  # Screens finished before any stop


if __name__ == "__main__":
    main()
