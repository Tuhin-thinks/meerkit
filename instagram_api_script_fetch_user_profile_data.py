import json
import pprint
from urllib.parse import quote

import requests

# ==============================================
# Script: Fetch User Profile Data
# Internal Name: fetch_user_profile_data
# ==============================================

url = "https://www.instagram.com/api/graphql"

headers = {
    "accept": "*/*",
    "accept-language": "en-GB,en;q=0.6",
    "content-type": "application/x-www-form-urlencoded",
    "dnt": "1",
    "origin": "https://www.instagram.com",
    "priority": "u=1, i",
    "referer": "https://www.instagram.com/the.nomad.canvas/",
    "sec-ch-ua": '"Not=A?Brand";v="99", "Brave";v="151", "Chromium";v="151"',
    "sec-ch-ua-full-version-list": '"Not=A?Brand";v="99.0.0.0", "Brave";v="151.0.0.0", "Chromium";v="151.0.0.0"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-model": '""',
    "sec-ch-ua-platform": '"Linux"',
    "sec-ch-ua-platform-version": '""',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "x-asbd-id": "359341",
    "x-csrftoken": "0ENw9yYuKJLJptycYolUcsV075Keilyg",
    "x-fb-friendly-name": "PolarisProfilePageContentQuery",
    "x-fb-lsd": "Wr_1XFWqS__YAylS91n-Dg",
    "x-ig-app-id": "936619743392459",
    "x-ig-max-touch-points": "0",
}

cookies = {
    "csrftoken": "0ENw9yYuKJLJptycYolUcsV075Keilyg",
    "datr": "2PPYadz1L6705BcpLMiKvjld",
    "ds_user_id": "72442672965",
    "ig_did": "727867C6-027D-4622-9605-7438653E7080",
    "ig_nrcb": "1",
    "mid": "adjz2AAEAAHT6sRoxy80KUYkMzBH",
    "oo": "v1%7C3%3A1781251003",
    "ps_l": "1",
    "ps_n": "1",
    "rur": "LLA%2C17841472268975334%2C1787158415%3A01ff678fcfe9058124b8416592b902aed5dd82f144743549ec340f04278528a6120e0d62",
    "sessionid": "72442672965%3A2Be4FjyBq8rOpr%3A23%3AAYh2FDrozUAKLhH5LceCIBfLsI82U9YW8zB12BO_vw",
    "wd": "1269x962",
}

variables = {
    "enable_integrity_filters": "true",
    "id": "72442672965",
    "__relay_internal__pv__PolarisCannesGuardianExperienceEnabledrelayprovider": "true",
    "__relay_internal__pv__PolarisCASB976ProfileEnabledrelayprovider": "false",
    "__relay_internal__pv__PolarisWebSchoolsEnabledrelayprovider": "false",
    "__relay_internal__pv__PolarisRepostsConsumptionEnabledrelayprovider": "false",
    "__relay_internal__pv__PolarisShortDramaEnabledrelayprovider": "false",
    "__relay_internal__pv__PolarisLongformEnabledrelayprovider": "false",
}
data = {
    "av": "17841472268975334",
    "doc_id": "27441298125552055",
    "fb_api_caller_class": "RelayModern",
    "fb_api_req_friendly_name": "PolarisProfilePageContentQuery",
    "fb_dtsg": "NAfyr8yFYYiMgO-PvVEEl0bX9fHhrDrs_qeSqfiekN8r7c3BWVgHnug:17854477105113577:1785927042",
    "jazoest": "26471",
    "lsd": "Wr_1XFWqS__YAylS91n-Dg",
    "server_timestamps": "true",
}

data_string = "&".join(f"{k}={v}" for k, v in data.items())
data_string += f"&variables={quote(json.dumps(variables))}"
response = requests.post(
    url,
    headers=headers,
    cookies=cookies,
    data=data_string,
)

print(response.status_code)
if response.status_code == 200:
    pprint.pprint(response.json(), indent=2)
else:
    print("Error: \n", response.text)
