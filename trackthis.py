from datetime import datetime
import platform
import socket
import json
import xmltodict
import aiohttp
import asyncio


class UPS:
    """
    Track UPS and shipments asyncronously for maximum performance.
    It also has the option of returning simplified tracking results which will have the same format for UPS and UPS.
    UPS API credentials are required. Credentials can be obtained by signing up here: https://www.ups.com/upsdeveloperkit

    Parameters:
    ups_username: UPS Account Username
    ups_password: UPS Account Password
    ups_license: UPS Account License
    """

    def __init__(self, ups_username: str, ups_password: str, ups_license: str):
        self.ups_username = ups_username
        self.ups_password = ups_password
        self.ups_license = ups_license

        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        self.ups_status_codes = {
            # status_rank is used in cases where multiple boxes are found for the same tracking number. In this case, the "highest" ranked status is used.
            "X": {"general_status": "Exception", "ups_status": "Exception", "status_rank": 9},
            "RS": {"general_status": "Return to Sender", "ups_status": "Returned to Shipper", "status_rank": 8},
            "NA": {"general_status": "Not Available", "ups_status": "Not Available", "status_rank": 7},
            "MV": {"general_status": "Cancelled", "ups_status": "Billing Information Voided", "status_rank": 6},
            "M": {"general_status": "Pre-Shipment", "ups_status": "Billing Information Received", "status_rank": 5},
            "P": {"general_status": "In Transit", "ups_status": "Pickup", "status_rank": 4},
            "I": {"general_status": "In Transit", "ups_status": "In Transit", "status_rank": 3},
            "O": {"general_status": "Out for Delivery", "ups_status": "Out for Delivery", "status_rank": 2},
            "D": {"general_status": "Delivered", "ups_status": "Delivered", "status_rank": 1}
        }

    def chunk_list(self, chunk_size, whole_list) -> list:
        """This function is used to split a list into multiple lists of a given size.
        Example:
        original_list = ["a", "b", "c", "d", "e"]
        list_chunks = chunk_list(2, original_list)
        list_chunks = [["a", "b"], ["c", "d"], ["e"]]

        Args:
            chunk_size (int): What should the length of each sublist be?
            whole_list ([type]): List of items.

        Returns:
            list: List of lists of given chunk_size length
        """
        chunks = [
            whole_list[i : i + chunk_size]
            for i in range(0, len(whole_list), chunk_size)
        ]
        return chunks

    def track_ups(self, tracking_list: list = [], simplify=True) -> list:
        """Use UPS API to track UPS shipments.
        Set simplify=True argument to only return basic tracking update in JSON format.
        The simplified format will match the track_usps simplified method.
        Args:
            tracking_list (list): List of UPS tracking numbers.
            simplify (bool, optional): Leave as false if you want the raw UPS response data.
                Set to True if you only need basic tracking updates. Defaults to True.

        Returns:
            list: Unordered list of USPS tracking data.
        """
        ups_requests = self._create_ups_request(tracking_list)
        main = self._track_ups(ups_requests)
        tracking_results = asyncio.run(main)
        if simplify is True:
            stan_tracking_results = self._simplify_ups(tracking_results)
            return stan_tracking_results
        else:
            return tracking_results

    def _create_ups_request(self, tracking_list) -> list:
        ups_requests = []
        for tracking_number in tracking_list:
            payload = {
                "Security": {
                    "UsernameToken": {
                        "Username": self.ups_username,
                        "Password": self.ups_password,
                    },
                    "UPSServiceAccessToken": {"AccessLicenseNumber": self.ups_license},
                },
                "TrackRequest": {
                    "Request": {"RequestAction": "Track", "RequestOption": "activity"},
                    "InquiryNumber": tracking_number,
                },
            }
            ups_requests.append(payload)
        return ups_requests

    async def _track_ups(self, ups_requests) -> list:
        """This function takes a list of UPS tracking numbers and uses the UPS API to get tracking updates.
        Note, this is an async function.
        Args:
            ups_requests (list): List of UPS tracking queries.

        Returns:
            list: List of UPS tracking results.
        """
        url = "https://onlinetools.ups.com/json/Track"
        tracking_results = []
        ups_failed = []
        async with aiohttp.ClientSession() as session:
            for request_data in ups_requests:
                async with session.get(url, json=request_data) as resp:
                    resp = await resp.json()
                    if resp.get("Fault") is not None:
                        ups_failed.append(
                            request_data.get("TrackRequest").get("InquiryNumber")
                        )
                    else:
                        tracking_results.append(resp)
            fail_rate = len(ups_failed) / len(ups_requests)
            if (fail_rate > 0.05):  # Print warning if funtion fails to get >=5% of tracking results
                print(f"Warning: Failed to get tracking data for {fail_rate:.0%} of shipments.")
            return tracking_results

    def _simplify_ups(self, tracking_results) -> list:
        stan_tracking_results = []
        for resp in tracking_results:
            package_data = resp.get("TrackResponse").get("Shipment").get("Package")
            tracking_number = resp.get("TrackResponse").get("Shipment").get("InquiryNumber").get("Value")
            if type(package_data) == list:
                overall_rank = 0
                for tracking_num in package_data:
                    tracking_activity = tracking_num.get("Activity")
                    if type(tracking_activity) == list:
                        latest_activity = tracking_activity[0]
                    else:
                        latest_activity = tracking_activity
                    latest_status = latest_activity.get("Status").get("Type")
                    try:
                        status_rank = self.ups_status_codes[latest_status].get("status_rank")
                    except:
                        status_rank = 0
                    if status_rank > overall_rank:
                        overall_activity = latest_activity
                        overall_rank = status_rank
                latest_activity = overall_activity
            else:
                overall_activity = package_data.get("Activity")
            if type(overall_activity) == list:
                package_activity = overall_activity[0]
            else:
                package_activity = overall_activity

            ups_status = {  # Simplified tracking schema
                "checkpointDate": None,
                "trackingNumber": None,
                "checkpointLocation": None,
                "trackingStatus": None,
                "checkpointStatusMessage": None,
            }

            activity_datetime_str = package_activity.get("Date") + package_activity.get("Time")
            ups_status["checkpointDate"] = datetime.strptime(activity_datetime_str, "%Y%m%d%H%M%S")

            ups_status["trackingNumber"] = tracking_number

            try:  # Get activity location data
                activity_location = package_activity["ActivityLocation"]["Address"]
                city = activity_location.get("City", "---")
                state_province_code = activity_location.get("StateProvinceCode", "---")
                country_code = activity_location.get("CountryCode", "---")
                ups_status["checkpointLocation"] = ", ".join([country_code, state_province_code, city]).upper()
            except:
                ups_status["checkpointLocation"] = None

            ups_code = package_activity["Status"]["Type"]
            ups_status["trackingStatus"] = self.ups_status_codes[ups_code].get("general_status", "Unknown")

            ups_status["checkpointStatusMessage"] = package_activity.get("Status").get("Description")
            stan_tracking_results.append(ups_status)
        return stan_tracking_results


class USPS:
    """
    Track USPS shipments asyncronously for maximum performance.
    It also has the option of returning simplified tracking results which will have the same format for UPS and UPS.
    USPS API credentials are required. Credentials can be obtained by signing up here: https://www.usps.com/business/web-tools-apis/

    Note: This library takes advantage of the USPS APIs ability to track 10 shipments per request. The USPS API automaically removes duplicate tracking numbers.
        This means if the USPS tracking number list contains duplicates, the list of tracking results may contain less items than the orignal list.

    Parameters:
    usps_username: USPS User ID
    company_name: The name of the company for the USPS account. This data is sent to the USPS API.
    """
    def __init__(self, usps_username: str, company_name: str):
        if usps_username == "":
            raise ValueError(f"'usps_username' attribute is required: {usps_username=}")

        if company_name == "":
            raise ValueError(f"'company_name' attribute is required: {company_name=}")

        self.usps_username = usps_username
        self.company_name = company_name

        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        self.usps_status_codes = {
            "Delivered": "Delivered",
            "Delivered to Agent": "Delivered",
            "Alert": "Exception",
            "In Transit": "In Transit",
            "Out for Delivery": "Out for Delivery",
            "Pre-Shipment": "Pre-Shipment",
            "Delivery Attempt": "Delivered - Delivery Attempt",
            "Available for Pickup": "Delivered - Available for Pickup"
        }

    def chunk_list(self, chunk_size, whole_list) -> list:
        """This function is used to split a list into multiple lists of a given size.
        Example:
        original_list = ["a", "b", "c", "d", "e"]
        list_chunks = chunk_list(2, original_list)
        list_chunks = [["a", "b"], ["c", "d"], ["e"]]

        Args:
            chunk_size (int): What should the length of each sublist be?
            whole_list ([type]): List of items.

        Returns:
            list: List of lists of given chunk_size length
        """
        chunks = [
            whole_list[i : i + chunk_size]
            for i in range(0, len(whole_list), chunk_size)
        ]
        return chunks

    def track_usps(self, tracking_list, simplify=True) -> list:
        """Use USPS API to track USPS shipments.
        By defualt this will return the full USPS response data (converted from XML to JSON).
        Set simplify=True argument to only return basic tracking update in JSON format.
        The simplified format will match the track_ups simplified method.
        Args:
            tracking_list (list): List of USPS tracking numbers.
            simplify (bool, optional): Leave as false if you want the raw USPS response data.
                Set to True if you only need basic tracking updates. Defaults to True.

        Returns:
            list: Unordered list of USPS tracking data.
        """
        tracking_chunks = self.chunk_list(10, tracking_list)
        usps_requests = self._create_usps_requests(tracking_chunks)
        main = self._track_usps(usps_requests)
        tracking_results = asyncio.run(main)

        if simplify is True:
            stan_tracking_results = self._simplify_usps(tracking_results)
            return stan_tracking_results
        else:
            return tracking_results

    def _create_usps_requests(self, tracking_chunks):
        """Create XML request body for use with USPS Tracking API.
        Args:
            tracking_chunks (list): List of lists contaning a maximum of 10 USPS tracking numbers each.
        Returns:
            list: List of USPS tracking data.
        """
        ip_address = socket.gethostbyname(socket.gethostname())
        usps_requests = []
        for chunk in tracking_chunks:
            xml_string = "".join([f'<TrackID ID="{chunk}"/>' for chunk in chunk])
            payload = f"""
                <TrackFieldRequest USERID="{self.usps_username}">
                <Revision>1</Revision>
                <ClientIp>{ip_address}</ClientIp>
                <SourceId>{self.company_name}</SourceId>
                {xml_string}
                </TrackFieldRequest>
            """
            request_data = f"https://secure.shippingapis.com/ShippingAPI.dll?API=TrackV2&XML={payload}"
            usps_requests.append(request_data)
        return usps_requests

    async def _track_usps(self, usps_requests):
        """Use USPS Package Tracking Fields API to track shipments.
        Convert USPS XML response into JSON.
        https://www.usps.com/business/web-tools-apis/track-and-confirm-api_files/track-and-confirm-api.htm#_Toc41911512

        Args:
            usps_requests (list): List of USPS tracking numbers.

        Returns:
            list: List of USPS tracking responses (converted from XML to JSON)
        """
        async with aiohttp.ClientSession() as session:
            tracking_results = []
            try:
                for request_data in range(len(usps_requests)):
                    async with session.get(usps_requests[request_data]) as resp:
                        xml_resp = await resp.text()
                        xml_to_string = json.dumps(xmltodict.parse(xml_resp))
                        json_resp = json.loads(xml_to_string).get("TrackResponse").get("TrackInfo")
                        tracking_results.extend(json_resp)
                return tracking_results
            except:
                print(f"Failed at request {usps_requests[request_data]}")
                return tracking_results

    def _simplify_usps(self, tracking_results):
        stan_tracking_results = []
        for i in tracking_results:
            try:
                tracking_number = i.get("@ID")
            except:
                continue
            try:
                track_summary = i.get("TrackSummary")
                event_time = track_summary.get("EventTime")
                event_date = track_summary.get("EventDate")
                event_dt = event_date + " " + event_time
                checkpoint_date = datetime.strptime(event_dt, "%B %d, %Y %I:%M %p")
            except:
                checkpoint_date = None
            try:
                event_city = track_summary.get("EventCity").upper()
                event_state = track_summary.get("EventState").upper()
                checkpoint_location = ", ".join([event_city, event_state, "US"])
            except:
                checkpoint_location = None
            try:
                checkpoint_status_message = (
                    i.get("Status") + " - " + i.get("StatusSummary")
                )
            except:
                checkpoint_status_message = None
            stantrack_usps = {
                "trackingNumber": tracking_number,
                "trackingStatus": self.usps_status_codes.get(i.get("StatusCategory")),
                "checkpointDate": checkpoint_date,
                "checkpointLocation": checkpoint_location,
                "checkpointStatusMessage": checkpoint_status_message,
            }
            stan_tracking_results.append(stantrack_usps)
        return stan_tracking_results
