# trackthis
This library can be used to track USPS and UPS shipments. 
It will return a standardized response containing basic tracking data by default. This is meant to make it easier when working with both UPS and USPS responses.

## Track UPS Orders
```
tracking_number_list = ["Z100", "Z101", Z102", "Z103", Z104", "Z105"]

ups_username = os.getenv("UPS_USERNAME")
ups_password = os.getenv("UPS_PASSWORD")
ups_license = os.getenv("UPS_LICENSE")
tracker_ups = trackthis.UPS(ups_username, ups_password, ups_license)

tracking_results = tracker_ups.track_ups(tracking_number_list)

print(tracking_results[0])

>> {
    "checkpointDate": datetime.datetime,
    "trackingNumber": str,
    "checkpointLocation" str,
    "trackingStatus" str,
    "checkpointStatusMessage" str
}
```

## Track USPS Orders
```
tracking_number_list = ["Z100", "Z101", Z102", "Z103", Z104", "Z105"]

usps_username = os.getenv("USPS_USERID")
company_name = "Clothing Shop Online"
tracker_usps = trackthis.USPS(usps_username, company_name)

tracking_results = tracker_usps.track_usps(tracking_number_list)

print(tracking_results[0])

>> {
    "checkpointDate": datetime.datetime,
    "trackingNumber": str,
    "checkpointLocation" str,
    "trackingStatus" str,
    "checkpointStatusMessage" str
}
```


### ToDo
- Integrate with EasyPost API to cover tracking for all other carriers.