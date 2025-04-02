import datetime
import pytz
import argparse
import sys
import os
import configparser

try:
    from dateutil.parser import isoparse
except ImportError:
    sys.exit("ERROR: Missing python dateutil module. Run 'pip install python-dateutil'.")

try:
    import teslapy
except ImportError:
    sys.exit("ERROR: Missing python teslapy module. Run 'pip install teslapy'.")


# Tesla mode for auto
MODE_SELF = "self_consumption"
MODE_TIME = "autonomous"

MID_PEEK = [("15:00", "16:00"), ("21:00", "00:00")]
PEEK = [("16:00", "21:00")]
SLEEP_PERIODS = [("00:30", "12:00"), ("16:30", "23:59")]

SCRIPTPATH = os.path.dirname(os.path.realpath(sys.argv[0]))
SCRIPTNAME = os.path.basename(sys.argv[0]).split('.')[0]
CONFIGNAME = CONFIGFILE = "set-reserve.conf"
AUTHFILE = f"{SCRIPTNAME}.auth"

print("Checking CONFIGFILE", CONFIGFILE)

# Load Configuration File
config = configparser.ConfigParser(allow_no_value=True)
if not os.path.exists(CONFIGFILE) and "/" not in CONFIGFILE:
    # Look for config file in script location if not found
    CONFIGFILE = f"{SCRIPTPATH}/{CONFIGFILE}"
if os.path.exists(CONFIGFILE):
    try:
        config.read(CONFIGFILE)

        # Get Tesla Settings
        TUSER = config.get('Tesla', 'USER')
        TAUTH = config.get('Tesla', 'AUTH')
        TDELAY = config.getint('Tesla', 'DELAY', fallback=1)

        if "/" not in TAUTH:
            TAUTH = f"{SCRIPTPATH}/{TAUTH}"

    except Exception as err:
        sys.exit(f"ERROR: Config file '{CONFIGNAME}' - {err}")


# Tesla Functions
def tesla_login(email):
    """
    Attempt to login to Tesla cloud account and display energy site details

    Returns a list of Tesla Energy sites if successful
    """
    print("-" * 40)
    print(f"Tesla account: {email}")
    print("-" * 40)

    # Create retry instance for use after successful login
    retry = teslapy.Retry(total=2, status_forcelist=(500, 502, 503, 504), backoff_factor=10)

    # Create Tesla instance
    tesla = teslapy.Tesla(email, cache_file=TAUTH)

    if not tesla.authorized:
        # Login to Tesla account and cache token
        state = tesla.new_state()
        code_verifier = tesla.new_code_verifier()

        try:
            print("Open the below address in your browser to login.\n")
            print(tesla.authorization_url(state=state, code_verifier=code_verifier))
        except Exception as err:
            sys.exit(f"ERROR: Connection failure - {err}")

        print("\nAfter login, paste the URL of the 'Page Not Found' webpage below.\n")

        tesla.close()
        tesla = teslapy.Tesla(email, retry=retry, state=state, code_verifier=code_verifier, cache_file=TAUTH)

        if not tesla.authorized:
            try:
                tesla.fetch_token(authorization_response=input("Enter URL after login: "))
                print("-" * 40)
            except Exception as err:
                sys.exit(f"ERROR: Login failure - {err}")
    else:
        # Enable retries
        tesla.close()
        tesla = teslapy.Tesla(email, retry=retry, cache_file=TAUTH)

    sitelist = {}
    try:
        # Get list of Tesla Energy sites
        for battery in tesla.battery_list():
            try:
                # Retrieve site id and name, site timezone and install date
                siteid = battery['energy_site_id']
                print(f"Get SITE_CONFIG for Site ID {siteid}")
                data = battery.api('SITE_CONFIG')
                print(data)
                if isinstance(data, teslapy.JsonDict) and 'response' in data:
                    sitename = data['response']['site_name']
                    sitetimezone = data['response']['installation_time_zone']
                    siteinstdate = isoparse(data['response']['installation_date'])
                else:
                    sys.exit(f"ERROR: Failed to retrieve SITE_CONFIG - unknown response: {data}")
            except Exception as err:
                sys.exit(f"ERROR: Failed to retrieve SITE_CONFIG - {err}")

            try:
                # Retrieve site current time
                print(f"Get SITE_DATA for Site ID {siteid}")
                data = battery.api('SITE_DATA')
                print(data)
                sitetime = isoparse(data['response']['timestamp'])
            except Exception:
                sitetime = "No 'live status' returned"

            # Add site if site id not already in the list
            if siteid not in sitelist:
                sitelist[siteid] = {}
                sitelist[siteid]['battery'] = battery
                sitelist[siteid]['name'] = sitename
                sitelist[siteid]['timezone'] = sitetimezone
                sitelist[siteid]['instdate'] = siteinstdate
                sitelist[siteid]['time'] = sitetime
    except Exception as err:
        sys.exit(f"ERROR: Failed to retrieve PRODUCT_LIST - {err}")

    # Print list of sites
    for siteid in sitelist:
        print(f"    Site ID: {siteid}")
        print(f"  Site name: {sitelist[siteid]['name']}")
        print(f"    Timezone: {sitelist[siteid]['timezone']}")
        print(f"  Installed: {sitelist[siteid]['instdate']}")
        print(f" System time: {sitelist[siteid]['time']}")
        print("-" * 40)

    return sitelist

def get_powerwall():
    """
    Retrieve Powerwall data
    """
    global dayloaded, power, soe

    print(f"Retrieving Powerwall data...")

    data = battery.api('SITE_CONFIG')['response']

    # print(data)
    return data

def set_mode(mode):
    """
    Set Powerwall operational mode
    """
    global dayloaded, power, soe

    print(f"Setting Powerwall operational mode to {mode}...")

    # self_consumption or autonomous
    data = battery.set_operation(mode)

    # print(data)
    return data


def get_level():
    """
    Retrieve Powerwall battery level backup reserve setting
    """
    global dayloaded, power, soe

    print(f"Retrieving Powerwall battery level reserve setting...")

    config = battery.api("SITE_CONFIG")["response"]
    site = battery.api("SITE_SUMMARY")["response"]
    # combine config and site data
    data = {**config, **site}
    print(data)
    return data


def set_level(level):
    """
    Set Powerwall battery level backup reserve setting
    """
    global dayloaded, power, soe

    print(f"Setting Powerwall battery level reserve setting...")

    data = battery.set_backup_reserve_percent(level)
    print(data)
    return data


def is_time_between(start_time_str, end_time_str, timezone_str='America/Los_Angeles'):
    """
    Checks if the current time in the specified timezone is between the given start and end times (inclusive).

    Args:
        start_time_str (str): Start time in HH:MM format (e.g., "00:00").
        end_time_str (str): End time in HH:MM format (e.g., "12:02").
        timezone_str (str, optional): The timezone to check against (e.g., 'America/Los_Angeles').
                                       Defaults to 'America/Los_Angeles'.

    Returns:
        bool: True if the current time is within the specified range, False otherwise.
    """
    try:
        target_tz = pytz.timezone(timezone_str)
        now_tz = datetime.datetime.now(target_tz)

        start_hour, start_minute = map(int, start_time_str.split(':'))
        end_hour, end_minute = map(int, end_time_str.split(':'))

        start_dt = now_tz.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        end_dt = now_tz.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)

        # Handle cases where the end time is on the next day (e.g., for overnight ranges)
        if end_dt < start_dt:
            end_dt = end_dt + datetime.timedelta(days=1)

        return start_dt <= now_tz <= end_dt

    except pytz.exceptions.UnknownTimeZoneError:
        print(f"Error: Unknown timezone '{timezone_str}'. Please provide a valid timezone.")
        return False
    except ValueError:
        print("Error: Invalid time format. Please use HH:MM for start and end times.")
        return False


def is_in_sleep_period():
    for period in SLEEP_PERIODS:
        if is_time_between(period[0], period[1]):
            print("Sleeping: ", period)
            return True
    return False


if __name__ == "__main__":

    is_in_sleep_period()

    # Login and get list of Tesla Energy sites
    sitelist = tesla_login(TUSER)

    # Check for energy sites
    if not sitelist:
        sys.exit("ERROR: No Tesla Energy sites found")

    # Get site from sitelist
    site = sitelist[list(sitelist.keys())[0]]

    # Get site battery and timezones
    battery = site['battery']
    sitetimezone = site['timezone']

    level_data = get_level()
    current_battery_level = int(level_data["percentage_charged"])
    print("Current level", current_battery_level)

    powerwall_data = get_powerwall()
    mode = powerwall_data['default_real_mode']
    pw_count = powerwall_data["battery_count"]
    print(f"Current Operational Mode: {mode} with {pw_count} Powerwalls")

    target_mode = MODE_TIME
    if mode == target_mode:
        sys.exit(f"Skip updating the mode which is already the target: {mode}")

    set_mode(target_mode)

    powerwall_data = get_powerwall()
    mode = powerwall_data['default_real_mode']
    pw_count = powerwall_data["battery_count"]
    print(f"READ: Current Operational Mode: {mode} with {pw_count} Powerwalls")
