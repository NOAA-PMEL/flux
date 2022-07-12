import pandas as pd
import json
import os
import pprint
import sdig.erddap.info as info


def dict_compare(d1, d2):
    d1_keys = set(d1.keys())
    d2_keys = set(d2.keys())
    shared_keys = d1_keys.intersection(d2_keys)
    added = d1_keys - d2_keys
    removed = d2_keys - d1_keys
    modified = {o : (d1[o], d2[o]) for o in shared_keys if d1[o] != d2[o]}
    same = set(o for o in shared_keys if d1[o] == d2[o])
    return added, removed, modified, same


all_standard_name_tables = {}
all_long_name_tables = {}

pp = pprint.PrettyPrinter(indent=4)

platform_file = 'oceansites_flux_list.json'
if platform_file is None:
    platform_file = os.getenv('PLATFORMS_JSON')

platform_json = None
if platform_file is not None:
    with open(platform_file) as platform_stream:
        platform_json = json.load(platform_stream)

datasets = platform_json['config']['datasets']
for dataset in datasets:
    if 'url' in dataset:
        url = dataset['url']

    dataset_info_url = info.get_info_url(url)
    info_for_dataset = pd.read_csv(dataset_info_url)
    variables, long_names, units, standard_names = info.get_variables(info_for_dataset)
    all_standard_name_tables[url] = standard_names
    all_long_name_tables[url] = long_names

first = {}
first_name = None

for index, table in enumerate(all_standard_name_tables):
    print(table)
    print('=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-')
    names = all_standard_name_tables[table]
    for standard_name in names:
        if ' ' in standard_name:
            print('{:<60s} {:<20s}'.format(standard_name, names[standard_name]))
    print('=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-')
    print('=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-')


for index, table in enumerate(all_standard_name_tables):
    if index == 0:
        first_name = table
        first = all_standard_name_tables[table]
    else:
        a, r, m, s = dict_compare(first, all_standard_name_tables[table])
        print('Table 1: ' + first_name)
        print('Table 2: ' + table)
        print('=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-')
        if len(a) > 0:
            print('In table 1, but not in 2:')
            print('\n')
            for aname in a:
                print('{:<60s} {:<20s}'.format(aname, all_standard_name_tables[first_name][aname]))
            print('\n')
        if len(r) > 0:
            print('In table 2, but not in table 1: ')
            print('\n')
            for rname in r:
                print('{:<60s} {:<20s}'.format(rname, all_standard_name_tables[table][rname]))
            print('\n')
        if len(m) > 0:
            print('same standard name with different short name: ')
            print('\n')
            for mname in m:
                print('{:<60s} {:<20s} {:<20s}'.format(mname, all_standard_name_tables[first_name][mname], all_standard_name_tables[table][mname]))
                print(mname + ' long_name from table 1 ' + all_long_name_tables[first_name][all_standard_name_tables[first_name][mname]])
                print(mname + ' long_name from table 2 ' + all_long_name_tables[table][all_standard_name_tables[table][mname]])
            print('\n')
        if len(s) > 0:
            print('standard names with same short name: ')
            print('\n')
            for sname in sorted(s):
                print('{:<60s} {:<20s} {:<20s}'.format(sname, all_standard_name_tables[first_name][sname], all_standard_name_tables[table][sname]))
            print('\n')

