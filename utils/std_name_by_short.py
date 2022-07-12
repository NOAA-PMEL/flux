import pandas as pd
import json
import os
import sdig.erddap.info as info

platform_file = 'oceansites_flux_list.json'
if platform_file is None:
    platform_file = os.getenv('PLATFORMS_JSON')

platform_json = None
if platform_file is not None:
    with open(platform_file) as platform_stream:
        platform_json = json.load(platform_stream)


std_to_short = {}

for platform in platform_json['config']['datasets']:
    url = platform['url']
    info_url = info.get_info_url(url)
    info_df = pd.read_csv(info_url)
    variables, long_names, units, standard_names = info.get_variables(info_df)
    for short_name in standard_names:
        std_name = standard_names[short_name]
        if std_name not in std_to_short:
            std_to_short[std_name] = [short_name]
        else:
            short_names = std_to_short[std_name]
            if short_name not in short_names:
                short_names.append(short_name)
                std_to_short[std_name] = short_names

for std_name in std_to_short:
    print(std_name, ' has ', std_to_short[std_name])
