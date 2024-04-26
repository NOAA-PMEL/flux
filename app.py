# Dash
import dash
from dash import Dash, callback, html, dcc, dash_table, Input, Output, State, MATCH, ALL, CeleryManager, DiskcacheManager
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px

# pytyony stuff
import os
import sys
import timeit

# Standard tools and utilities
import pandas as pd
import json
import pprint
import numpy as np
import datetime
import flask
import urllib

import diskcache

import celery
from celery import Celery
from celery.schedules import crontab

# My stuff
from sdig.erddap.info import Info

version = 'v1.5.3'  # units in the legend
empty_color = '#999999'
has_data_color = 'black'

month_step = 60*60*24*30.25
d_format = "%Y-%m-%d"

height_of_row = 450
legend_gap = height_of_row
line_rgb = 'rgba(.04,.04,.04,.2)'
plot_bg = 'rgba(1.0, 1.0, 1.0 ,1.0)'

sub_sample_limit = 88000

have_data_url = 'https://data.pmel.noaa.gov/pmel/erddap/tabledap'


y_pos_1_4 = [.999, .73225, .447, 0.161]
t_pos_1_4 = [.0005, .0005, .018, .036]

y_pos_2 = [.999, .390]
t_pos_2 = [.0005, .048]

discover_error = '''
You must configure a DISDOVERY_JSON env variable pointing to the JSON file that defines the which collections
of variables are to be in the discovery radio button list.
'''

graph_config = {'displaylogo': False, 'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                'doubleClick': 'reset+autosize',
                'toImageButtonOptions': {'height': None, 'width': None, },
                }

# platform_file = os.getenv('PLATFORM_JSON')
platform_file = 'oceansites_flux_list.json'
if platform_file is None:
    platform_file = os.getenv('PLATFORMS_JSON')

platform_json = None
if platform_file is not None:
    with open(platform_file) as platform_stream:
        platform_json = json.load(platform_stream)

variables_by_did = {}
locations_by_did = {}
units_by_did = {}

for dataset in platform_json['config']['datasets']:
    url = dataset['url']
    locations_url = dataset['locations']
    did = url[url.rindex('/') + 1:]
    dataset['id'] = did
    info = Info(url)
    title = info.get_title()
    dataset['title'] = title
    variables_list, long_names, units, standard_names, d_types = info.get_variables()
    units_by_did[did] = units
    variables_by_did[did] = variables_list
    mdf = pd.read_csv(locations_url, skiprows=[1],
                      dtype={'wmo_platform_code': str, 'site_code': str, 'latitude': np.float64, 'longitude': np.float64})
    mdf['did'] = did
    if mdf.shape[0] > 1 and mdf.site_code.nunique() <= 1:
        adf = mdf.mean(axis=0, numeric_only=True)
        adf['site_code'] = mdf['site_code'].iloc[0]
        mdf = pd.DataFrame(columns=['latitude', 'longitude', 'site_code'], index=[0], )
        mdf['latitude'] = adf.loc['latitude']
        mdf['longitude'] = adf.loc['longitude']
        mdf['site_code'] = adf.loc['site_code']
        mdf['wmo_platform_code'] = adf.loc['wmo_platform_code']
    locations_by_did[did] = json.dumps(mdf.to_json())

pp = pprint.PrettyPrinter(indent=4)

ESRI_API_KEY = os.environ.get('ESRI_API_KEY')

discovery_file = 'flux_discovery.json'
if discovery_file is None:
    discovery_file = os.getenv('DISCOVERY_FILE')

if discovery_file is not None:
    with open(discovery_file) as discovery_stream:
        discover_json = json.load(discovery_stream)
else:
    print('No config information found')
    sys.exit(-1)

radio_options = []
for key in discover_json['discovery']:
    q = discover_json['discovery'][key]
    radio_options.append({'label': q['question'], 'value': key})


all_start = None
all_end = None
all_start_seconds = 999999999999999
all_end_seconds = -999999999999999

for dataset in platform_json['config']['datasets']:
    url = dataset['url']
    my_info = Info(url)
    start_date, end_date, start_date_seconds, end_date_seconds = my_info.get_times()
    if start_date_seconds < all_start_seconds:
        all_start_seconds = start_date_seconds
        all_start = start_date
    if end_date_seconds > all_end_seconds:
        all_end_seconds = end_date_seconds
        all_end = end_date

time_marks = Info.get_time_marks(all_start_seconds, all_end_seconds)

celery_app = Celery(broker=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"), backend=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"))
if os.environ.get("DASH_ENTERPRISE_ENV") == "WORKSPACE":
    # For testing...
    # import diskcache
    cache = diskcache.Cache("./cache")
    background_callback_manager = DiskcacheManager(cache)
else:
    # For production...
    background_callback_manager = CeleryManager(celery_app)

app = dash.Dash(__name__,
                external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.BOOTSTRAP],
                background_callback_manager=background_callback_manager,
                )

app._favicon = 'favicon.ico'
app.title = 'Flux'
server = app.server




app.layout = \
    html.Div(
        style={'padding-left': '15px', 'padding-right': '25px'},
        children=[
            dcc.Location(id='location', refresh=False),
            dcc.Store(id='active-platforms'),
            dcc.Store(id='inactive-platforms'),
            dcc.Store(id='selected-platform'),
            dcc.Store(id='map-info'),
            dcc.Store(id='initial-time-start'),  # time from initial load query string
            dcc.Store(id='initial-time-end'),  # time from initial load query string
            dcc.Store(id='initial-site'),  # A site coming in on the query string
            html.Div(id='data-div', style={'display': 'none'}),
            dbc.Navbar(
                [
                    # Use row and col to control vertical alignment of logo / brand
                    dbc.Row(
                        style={'width': '100%'},
                        align="center",
                        children=[
                            dbc.Col(width=2, children=[
                                html.Img(src='assets/os_logo.gif',
                                         style={'height': '97px', 'width': '150px'})
                            ]),
                            dbc.Col(width=3, style={'display': 'flex', 'align-items': 'left'}, children=[
                                html.A(
                                    dbc.NavbarBrand(
                                        'Flux Data Discovery', className="ml-2",
                                        style={
                                            'padding-top': '160px',
                                            'font-size': '2.5em',
                                            'font-weight': 'bold'
                                        }
                                    ),
                                    href='https://www.pmel.noaa.gov/gtmba/oceansites',
                                    style={'text-decoration': 'none'}
                                )]
                            ),
                            dbc.Col(width=4),
                            # dbc.Col(width=4, children=[
                            #     html.Div(children=[
                            #     html.Div('Parts of the US government are closed. This site will not be updated; however, NOAA websites and social media channels necessary to protect lives and property will be maintained. See ', style={'display':'inline'}), 
                            #     html.A('www.weather.gov', href='https://www.weather.gov', style={'display':'inline'}), 
                            #     html.Div(' for critical weather information. To learn more, see ', style={'display': 'inline'}), 
                            #     html.A('www.commerce.gov', href='https://www.commerce.gov', style={'display':'inline'}), 
                            #     html.Div('.', style={'display':'inline'}),
                            #     ], style={'display':'inline'})
                            # ]),
                            dbc.Col(width=3, children=[
                                dcc.Loading(id='nav-loader', children=[
                                    html.Div(id='loading-div'),
                                    html.Div(children=[
                                        dbc.Button("Download Data", id='download-button', className="me-1"),
                                        dbc.Modal(children=
                                            [
                                                dbc.ModalHeader(dbc.ModalTitle("Download Data")),
                                                dbc.ModalBody(id='download-body'),
                                                dbc.ModalFooter(
                                                    dbc.Button(
                                                        "Close", id="close-download", className="ms-auto", n_clicks=0
                                                    )
                                                ),
                                            ],
                                            id="download-dialog",
                                            is_open=False,
                                        )
                                    ]),
                                ])
                            ])
                        ]
                    )
                ]
            ),
            dbc.Row(children=[
                dbc.Col(width=3, children=[
                    dbc.Card(children=[
                        dbc.CardHeader(children=["Discover:"]),
                        dbc.CardBody(children=[
                            dbc.RadioItems(
                                options=radio_options,
                                id="radio-items",
                            ),
                        ])
                    ]),
                    dbc.Card(children=[
                        dbc.CardHeader(children=['In the selected time range:']),
                        dbc.Row(children=[
                            dbc.Col(width=6, children=[
                                dbc.Card(children=[
                                    dbc.CardHeader(children=['Start Date']),
                                ]),
                                dbc.Input(id='start-date', debounce=True, value=all_start)
                            ]),
                            dbc.Col(width=6, children=[
                                dbc.Card(children=[
                                    dbc.CardHeader(children=['End Date']),
                                ]),
                                dbc.Input(id='end-date', debounce=True, value=all_end)
                            ])
                        ]),
                        dbc.Row(children=[
                            dbc.Col(width=12, children=[
                                html.Div(style={'padding-right': '40px', 'padding-left': '40px',
                                                'padding-top': '20px', 'padding-bottom': '45px'}, children=[
                                    dcc.RangeSlider(id='time-range-slider',
                                                    value=[all_start_seconds,all_end_seconds],
                                                    min=all_start_seconds,
                                                    max=all_end_seconds,
                                                    step=month_step,
                                                    marks=time_marks,
                                                    updatemode='mouseup',
                                                    allowCross=False)
                                ])
                            ])
                        ]),
                    ]),
                ]),
                dbc.Col(width=9, children=[
                    dbc.Card(children=[
                        dbc.CardHeader([
                            'Select the type of data and date range. Black dots have data, gray dots do not.',
                            dcc.Loading(html.Div(id='map-loading'))
                        ]),
                        dbc.CardBody(
                            dcc.Graph(id='location-map', config=graph_config),
                        )
                    ])
                ])
            ]),
            dbc.Row(id='plot-row', style={'display': 'none'}, children=[
                dbc.Col(width=12, children=[
                    dbc.Card(id='plot-card', children=[
                        dbc.CardHeader(id='plot-card-title'),
                        dbc.CardBody(id='plot-card-body', children=[
                            dcc.Loading(
                                dcc.Graph(id='plot-graph', config=graph_config)
                            )
                        ])
                    ])
                ])
            ]),
            dbc.Row(style={'margin-bottom': '10px'}, children=[
                dbc.Col(width=12, children=[
                    dbc.Card(children=[
                        dbc.Row(children=[
                            dbc.Col(width=1, children=[
                                html.Img(src='https://www.pmel.noaa.gov/sites/default/files/PMEL-meatball-logo-sm.png',
                                         height=100,
                                         width=100),
                            ]),
                            dbc.Col(width=10, children=[
                                html.Div(children=[
                                    dcc.Link('National Oceanic and Atmospheric Administration',
                                             href='https://www.noaa.gov/'),
                                ]),
                                html.Div(children=[
                                    dcc.Link('Pacific Marine Environmental Laboratory', href='https://www.pmel.noaa.gov/'),
                                ]),
                                html.Div(children=[
                                    dcc.Link('oar.pmel.webmaster@noaa.gov', href='mailto:oar.pmel.webmaster@noaa.gov')
                                ]),
                                html.Div(children=[
                                    dcc.Link('DOC |', href='https://www.commerce.gov/'),
                                    dcc.Link(' NOAA |', href='https://www.noaa.gov/'),
                                    dcc.Link(' OAR |', href='https://www.research.noaa.gov/'),
                                    dcc.Link(' PMEL |', href='https://www.pmel.noaa.gov/'),
                                    dcc.Link(' Privacy Policy |', href='https://www.noaa.gov/disclaimer'),
                                    dcc.Link(' Disclaimer |', href='https://www.noaa.gov/disclaimer'),
                                    dcc.Link(' Accessibility', href='https://www.pmel.noaa.gov/accessibility')
                                ])
                            ]),
                            dbc.Col(width=1, children=[
                                html.Div(style={'font-size': '1.0em', 'position': 'absolute', 'bottom': '0'},
                                         children=[version])
                            ])
                        ])
                    ])
                ])
            ])
        ]
    )


def get_blank(platform, b_start_date, b_end_date):
    message = 'No data available at ' + platform + ' for ' + b_start_date + ' to ' + b_end_date
    blank_graph = go.Figure(go.Scatter(x=[0, 1], y=[0, 1], showlegend=False))
    blank_graph.add_trace(go.Scatter(x=[0, 1], y=[0, 1], showlegend=False))
    blank_graph.update_traces(visible=False)
    blank_graph.update_layout(
        xaxis={"visible": False},
        yaxis={"visible": False},
        title=message,
        plot_bgcolor=plot_bg,
        annotations=[
            {
                "text": message,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {
                    "size": 14
                }
            },
        ]
    )
    return blank_graph


def make_gaps(pdf, fre):
    if pdf.shape[0] > 3:
        # This magic inserts missing values between rows that are more than two deltas apart.
        # Make time the index to the data
        pdf2 = pdf.set_index('time')
        pdf2 = pdf2[~pdf2.index.duplicated()]
        # make a index at the expected delta
        fill_dates = pd.date_range(pdf['time'].iloc[0], pdf['time'].iloc[-1], freq=fre)
        # sprinkle the actual values out along the new time axis, by combining the regular
        # intervals index and the data index
        all_dates = fill_dates.append(pdf2.index)
        all_dates = all_dates[~all_dates.duplicated()]
        fill_sort = sorted(all_dates)
        # reindex the data which causes NaNs everywhere in the regular index that don't
        # exactly match the data, with the data in between the NaNs
        pdf3 = pdf2.reindex(fill_sort)
        # remove the NaN rows that are by themselves because there is data near enough
        mask1 = ~pdf3['site_code'].notna() & ~pdf3['site_code'].shift().notna()
        mask2 = pdf3['site_code'].notna()
        pdf4 = pdf3[mask1 | mask2]
        # Reindex to 0 ... N
        pdf = pdf4.reset_index()
    return pdf


@app.callback(
    [
        Output('initial-time-start', 'data'),
        Output('initial-time-end', 'data'),
        Output('radio-items', 'value'),
        Output('initial-site', 'data')
    ],
    [
        Input('data-div', 'n_clicks')
    ],
    [
        State('location', 'search')
    ]
)
def process_query(aclick, qstring):
    qurl = flask.request.referrer
    parts = urllib.parse.urlparse(qurl)
    params = urllib.parse.parse_qs(parts.query)
    # get defaults from initial load
    initial_start_time = all_start
    initial_end_time = all_end
    dq = ''
    if 'start_date' in params:
        initial_start_time = params['start_date'][0]
    if 'end_date' in params:
        initial_end_time = params['end_date'][0]
    if 'q' in params:
        dq = params['q'][0]
    initial_site_json = {}
    if 'site_code' in params and 'lat' in params and 'lon' in params:
        initial_site_code = params['site_code'][0]
        initial_lat = params['lat'][0]
        initial_lon = params['lon'][0]
        initial_site_json = {'site_code': initial_site_code, 'lat': initial_lat, 'lon': initial_lon}
    return [initial_start_time, initial_end_time, dq, json.dumps(initial_site_json)]


@app.callback(
    Output("download-dialog", "is_open"),
    [Input("download-button", "n_clicks"), Input("close-download", "n_clicks")],
    [State("download-dialog", "is_open")],
)
def toggle_modal(n1, n2, is_open):
    if n1 or n2:
        return not is_open
    return is_open


@app.callback([
    Output('map-info', 'data')
],[
    Input('location-map', 'relayoutData')
]
)
def record_map_change(relay_data):
    center = {'lon': 0.0, 'lat': 0.0}
    zoom = 1.4
    if relay_data is not None:
        if 'mapbox.center' in relay_data:
            center = relay_data['mapbox.center']
        if 'mapbox.zoom' in relay_data:
            zoom = relay_data['mapbox.zoom']
    map_info = {'center': center, 'zoom': zoom}
    return [json.dumps(map_info)]


@app.callback(
    [
        Output('active-platforms', 'data'),
        Output('inactive-platforms', 'data'),
        Output('map-loading', 'children')
    ],
    [
        Input('start-date', 'value'),
        Input('end-date', 'value'),
        Input('radio-items', 'value'),
    ], prevent_initial_call=True
)
def update_platform_state(in_start_date, in_end_date, in_data_question):
    time0 = timeit.default_timer()
    time_constraint = ''
    all_with_data = None
    all_without_data = None
    # check to see which platforms have data for the current variables
    if in_start_date is not None and in_end_date is not None:
        n_start_obj = datetime.datetime.strptime(in_start_date, d_format)
        n_start_obj.replace(day=1, hour=0)
        time_constraint = time_constraint + '&time>=' + n_start_obj.isoformat()

        n_end_obj = datetime.datetime.strptime(in_end_date, d_format)
        n_end_obj.replace(day=1, hour=0)
        time_constraint = time_constraint + '&time<=' + n_end_obj.isoformat()
        if n_start_obj.year != n_end_obj.year:
            count_by = '1year'
        elif n_start_obj.year == n_end_obj.year and n_start_obj.month != n_end_obj.month:
            count_by = '1month'
        else:
            count_by = '1day'
    time1 = timeit.default_timer()
    if in_data_question is not None and len(in_data_question) > 0:
        for qin in discover_json['discovery']:
            if qin == in_data_question:
                search_params = discover_json['discovery'][qin]['search']
                for search in search_params:
                    vars_to_get = search['short_names'].copy()
                    vars_to_get.append('time')
                    vars_to_get.append('site_code')
                    short_names = ','.join(vars_to_get)
                    # join_type == "or" then sum of short name columns > 0.
                    # join_type == "and" then s1 > 0 && s2 > 0 ...
                    join_type = search['join']
                    for dataset_to_check in search['datasets']:
                        cur_did = dataset_to_check[dataset_to_check.rindex('/')+1:]
                        locations_to_map = pd.read_json(json.loads(locations_by_did[cur_did]),
                                                        dtype={'site_code': str,
                                                               'latitude': np.float64,
                                                               'longitude': np.float64})
                        have_url = dataset_to_check + '.csv?' + short_names + time_constraint
                        have = None
                        try:
                            have = pd.read_csv(have_url, skiprows=[1])
                        except:
                            pass
                        if have is not None:
                            csum = have.groupby(['site_code']).sum().reset_index()
                            csum['site_code'] = csum['site_code'].astype(str)
                            sum_n = None
                            if join_type == 'or':
                                csum['has_data'] = csum[search['short_names']].sum(axis=1)
                                csum = csum.sort_values('site_code')
                                locations_to_map = locations_to_map.sort_values('site_code')
                                sum_n = csum.loc[csum['has_data'] > 0]
                            if join_type == 'and':
                                chk_vars = search['short_names']
                                criteria = ''
                                for vix, v in enumerate(chk_vars):
                                    if vix > 0:
                                        criteria = criteria + ' & '
                                    criteria = criteria + '(csum[\'' + v + '\']' + ' > 0)'
                                criteria = 'csum[(' + criteria + ')]'
                                # eval dereferences all the stuff in the string and runs it
                                sum_n = pd.eval(criteria)
                            if sum_n is not None and sum_n.shape[0] > 0:
                                # sum_n is the platforms that have data.
                                # This merge operation (as explained here:
                                # https://stackoverflow.com/questions/53645882/pandas-merging-101/53645883#53645883)
                                # combines the locations data frame with
                                # the information about which sites have observations to make something
                                # that can be plotted.
                                some_data = locations_to_map.merge(sum_n, on='site_code', how='inner')
                                some_data['platform_color'] = has_data_color
                                if all_with_data is None:
                                    all_with_data = some_data
                                else:
                                    all_with_data = pd.concat([all_with_data, some_data])
                                criteria = locations_to_map.site_code.isin(some_data.site_code) == False
                                no_data = locations_to_map.loc[criteria].reset_index()
                                no_data['platform_color'] = empty_color
                                if all_without_data is None:
                                    all_without_data = no_data
                                else:
                                    all_without_data = pd.concat([all_without_data, no_data])
                        else:
                            locations_to_map['platform_color'] = empty_color
                            if all_without_data is None:
                                all_without_data = locations_to_map
                            else:
                                all_without_data = pd.concat([all_without_data, locations_to_map])
    else:
        for map_did in locations_by_did:
            locations_to_map = pd.read_json(json.loads(locations_by_did[map_did]),
                                            dtype={'wmo_platform_code': str, 'site_code': str, 'latitude': np.float64, 'longitude': np.float64})

            locations_to_map['platform_color'] = empty_color
            if all_without_data is None:
                all_without_data = locations_to_map
            else:
                all_without_data = pd.concat([all_without_data, locations_to_map])
    locations_with_data = json.dumps(pd.DataFrame(columns=['latitude', 'longitude', 'site_code', 'platform_color'], index=[0],).to_json())
    locations_without_data = json.dumps(pd.DataFrame(columns=['latitude', 'longitude', 'site_code', 'platform_color'], index=[0],).to_json())
    time2 = timeit.default_timer()
    if all_with_data is not None:
        all_with_data.reset_index(inplace=True, drop=True)
        locations_with_data = json.dumps(all_with_data.to_json())
    if all_without_data is not None:
        all_without_data.reset_index(inplace=True, drop=True)
        locations_without_data = json.dumps(all_without_data.to_json())
    time3 = timeit.default_timer()
    # print('Total time: ' + convertSeconds(time3-time0))
    # print('\tSetup dates: ' + convertSeconds(time1-time0))
    # print('\tRead counts ERDDAP: ' + convertSeconds(time2-time1))
    # print('\tReset Indexes: ' + convertSeconds(time3-time2))
    return [locations_with_data, locations_without_data, '']


def convertSeconds(in_seconds):
    seconds=int(in_seconds)%60
    minutes=int(in_seconds/(60))%60
    hours=int(in_seconds/(60*60))%24
    return str(hours) + ":" + str(minutes) + ":" + str(seconds)

@app.callback(
    [
        Output('location-map', 'figure'),
    ],
    [
        Input('active-platforms', 'data'),
        Input('inactive-platforms', 'data'),
        Input('selected-platform', 'data'),
    ],
    [
        State('map-info', 'data')
    ], prevent_initial_call=True)
def make_location_map(in_active_platforms, in_inactive_platforms, in_selected_platform, in_map):
    tp0 = timeit.default_timer()
    center = {'lon': 0.0, 'lat': 0.0}
    zoom = 1.4
    if in_map is not None:
        map_inf = json.loads(in_map)
        center = map_inf['center']
        zoom = map_inf['zoom']
    location_map = go.Figure()
    selected_plat = None
    tp1 = timeit.default_timer()
    if in_selected_platform is not None:
        selected_plat = json.loads(in_selected_platform)
    tp2 = timeit.default_timer()
    if in_active_platforms is not None and in_inactive_platforms is not None:
        data_for_yes = pd.read_json(json.loads(in_active_platforms))
        data_for_no = pd.read_json(json.loads(in_inactive_platforms))
        no_trace = None
        if data_for_no.shape[0] > 0:
            no_trace = go.Scattermapbox(lat=data_for_no['latitude'],
                                        lon=data_for_no['longitude'],
                                        hovertext=data_for_no['site_code'],
                                        hoverinfo='lat+lon+text',
                                        customdata=data_for_no['site_code'],
                                        marker={'color': data_for_no['platform_color'], 'size': 10},
                                        mode='markers')
        yes_trace = None
        if data_for_yes.shape[0] > 0:
            yes_trace = go.Scattermapbox(lat=data_for_yes['latitude'],
                                         lon=data_for_yes['longitude'],
                                         hovertext=data_for_yes['site_code'],
                                         hoverinfo='lat+lon+text',
                                         customdata=data_for_yes['site_code'],
                                         marker={'color': data_for_yes['platform_color'], 'size': 10},
                                         mode='markers')
        if no_trace is not None:
            location_map.add_trace(no_trace)
        if yes_trace is not None:
            location_map.add_trace(yes_trace)
    tp3 = timeit.default_timer()
    if selected_plat is not None and 'lat' in selected_plat and 'lon' in selected_plat and 'site_code' in selected_plat:
        yellow_trace = go.Scattermapbox(lat=[selected_plat['lat']],
                                        lon=[selected_plat['lon']],
                                        hovertext=[selected_plat['site_code']],
                                        hoverinfo='lat+lon+text',
                                        customdata=[selected_plat['site_code']],
                                        marker={'color': 'yellow', 'size': 15},
                                        mode='markers')
        location_map.add_trace(yellow_trace)
    tp4 = timeit.default_timer()
    location_map.update_layout(
        showlegend=False,
        mapbox_style="white-bg",
        mapbox_layers=[
            {
                "below": 'traces',
                "sourcetype": "raster",
                "sourceattribution": "Powered by Esri",
                "source": [
                    "https://ibasemaps-api.arcgis.com/arcgis/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}?token=" + ESRI_API_KEY
                ]
            }
        ],
        mapbox_zoom=zoom,
        mapbox_center=center,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend=dict(
            orientation="v",
            x=-.01,
        ),
        modebar_orientation='v',
    )
    tp5 = timeit.default_timer()
    # print('Make dot map:')
    # print('\tTotal time: ' + convertSeconds(tp5 - tp0))
    # print('\t\tRead map config: ' + convertSeconds(tp1 - tp0))
    # print('\t\tRead platforms: ' + convertSeconds(tp2 - tp1))
    # print('\t\tBlack/Grey Trace: ' + convertSeconds(tp3 - tp2))
    # print('\t\tYellow dot: ' + convertSeconds(tp4 - tp3))
    # print('\t\tMap config: ' + convertSeconds(tp5 - tp4))
    return [location_map]


@app.callback(
    [
        Output('selected-platform', 'data'),
    ],
    [
        Input('location-map', 'clickData'),
        Input('initial-site', 'data')
    ], prevent_initial_call=True
)
def update_selected_platform(click, initial_site):
    selection = None
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == 'initial-site':
        selection = initial_site
    else:
        if click is not None:
            if 'points' in click:
                point_dict = click['points'][0]
                selected_platform = point_dict['customdata']
                selected_lat = point_dict['lat']
                selected_lon = point_dict['lon']
                selection = json.dumps({'site_code': selected_platform, 'lat': selected_lat, 'lon': selected_lon})
    return [selection]


@app.callback(
    [
        Output('plot-row', 'style'),
        Output('plot-card-title', 'children'),
        Output('plot-graph', 'figure'),
        Output('download-body', 'children'),
        Output('location', 'search'),
        Output('loading-div', 'children')
    ],
    [
        Input('selected-platform', 'data'),
        Input('start-date', 'value'),
        Input('end-date', 'value'),
        Input('active-platforms', 'data'),
    ],
    [
        State('radio-items', 'value'),
    ], prevent_initial_call=True, background=True
)
def plot_from_selected_platform(selection_data, plot_start_date, plot_end_date, active_platforms, question_choice,):
    p0 = timeit.default_timer()
    row_style = {'display': 'block'}
    list_group = html.Div()
    list_group.children = []
    # print('+_+_+_+_+_+_+_+ Starting plot callback...')
    if selection_data is not None:
        selected_json = json.loads(selection_data)
        if 'site_code' in selected_json:
            selected_platform = selected_json['site_code']
        else:
            raise dash.exceptions.PreventUpdate
    else:
        raise dash.exceptions.PreventUpdate
    if active_platforms is not None:
        active = pd.read_json(json.loads(active_platforms))
    p1 = timeit.default_timer()
    if active is not None and selected_platform is not None:
        plot_time = '&time>='+plot_start_date+'&time<='+plot_end_date
        to_plot = active.loc[active['site_code'] == selected_platform]
        if to_plot.empty:
            return [row_style, plot_title, get_blank(selected_platform, plot_start_date, plot_end_date), list_group, '', '']
        dids = to_plot['did'].to_list()
        num_rows = len(dids)
        current_search = None
        for a_search in discover_json['discovery']:
            if a_search == question_choice:
                current_search = discover_json['discovery'][a_search]
        figure = make_subplots(rows=num_rows, cols=1, row_heights=[450]*num_rows, shared_xaxes='all', shared_yaxes=False, subplot_titles=dids, vertical_spacing=(.275/num_rows))
        dataset_idx = 0
        sub_plot_titles = []
        sub_plot_bottom_titles = []
        if len(dids) == 2:
            y_pos = y_pos_2.copy()
            t_pos = t_pos_2.copy()
        else:
            y_pos = y_pos_1_4.copy()
            t_pos = t_pos_1_4.copy()
        p2 = timeit.default_timer()
        for p_did in dids:
            current_dataset = next(
                (item for item in platform_json['config']['datasets'] if item['id'] == p_did), None)
            p_url = current_dataset['url']
            for search in current_search['search']:
                link_group = dbc.ListGroup(horizontal=True)
                link_group.children = []
                for pd_data_url in search['datasets']:
                    if p_did in pd_data_url:
                        dataset_idx = dataset_idx + 1
                        vlist = search['short_names'].copy()
                        pvars = ','.join(vlist+['time', 'site_code'])
                        plot_title = 'Plot of ' + ','.join(vlist) + ' at ' + selected_platform
                        p_url = p_url + '.csv?' + pvars + plot_time + '&site_code="' + selected_platform + '"'
                        print('Making a plot of ' + p_url)
                        df = pd.read_csv(p_url, skiprows=[1])
                        sub_title = selected_platform
                        bottom_title = current_dataset['title']
                        if df.shape[0] > sub_sample_limit:
                            df = df.sample(n=sub_sample_limit).sort_values('time')
                            sub_title = sub_title + ' (timeseries sub-sampled to ' + str(sub_sample_limit) + ' points) '
                        sub_plot_titles.append(sub_title)
                        sub_plot_bottom_titles.append(bottom_title)
                        l_labels = []
                        for n, v in enumerate(vlist):
                            if v in units_by_did[p_did]:
                                l_labels.append(v + ' (' + units_by_did[p_did][v] + ')')
                            else:
                                l_labels.append(v)
                        lines = px.line(df, x='time', y=vlist, labels=l_labels)
                        legend_name = 'legend'
                        if dataset_idx > 1:
                            legend_name = 'legend' + str(dataset_idx)
                        lines.update_traces(legend=legend_name)
                        for ifig, fig in enumerate(list(lines.select_traces())):
                            nfig = go.Figure(fig)
                            nfig.update_traces(name=l_labels[ifig])
                            figure.add_trace(list(nfig.select_traces())[0], row=dataset_idx, col=1)
                        meta_item = dbc.ListGroupItem(current_dataset['title'] + ' at ' + selected_platform, href=current_dataset['url'], target='_blank')
                        link_group.children.append(meta_item)
                        read_data = pd.read_csv(p_url, skiprows=[1])
                        item = dbc.ListGroupItem('.html', href=p_url.replace('.csv', '.htmlTable'), target='_blank')
                        link_group.children.append(item)
                        item = dbc.ListGroupItem('.csv', href=p_url.replace('.htmlTable', '.csv'), target='_blank')
                        link_group.children.append(item)
                        item = dbc.ListGroupItem('.nc', href=p_url.replace('.csv', '.ncCF'), target='_blank')
                        link_group.children.append(item)
                        list_group.children.append(link_group)
        p3 = timeit.default_timer()
        figure.update_layout(height=height_of_row*num_rows, showlegend=True)
        figure.update_layout(plot_bgcolor=plot_bg, hovermode='x',)
        figure.update_xaxes({
                'ticklabelmode': 'period',
                'showticklabels': True,
                'gridcolor': line_rgb,
                'zeroline': True,
                'zerolinecolor': line_rgb,
                'showline': True,
                'linewidth': 1,
                'linecolor': line_rgb,
                'mirror': True,
                'tickfont': {'size': 16},
                'tickformatstops' : [
                    dict(dtickrange=[1000, 60000], value="%H:%M:%S\n%d%b%Y"),
                    dict(dtickrange=[60000, 3600000], value="%H:%M\n%d%b%Y"),
                    dict(dtickrange=[3600000, 86400000], value="%H:%M\n%d%b%Y"),
                    dict(dtickrange=[86400000, 604800000], value="%e\n%b %Y"),
                    dict(dtickrange=[604800000, "M1"], value="%b\n%Y"),
                    dict(dtickrange=["M1", "M12"], value="%b\n%Y"),
                    dict(dtickrange=["M12", None], value="%Y")
                ]
        })
        figure.update_yaxes({'gridcolor': line_rgb,
                             'zeroline': True,
                             'zerolinecolor': line_rgb,
                             'showline': True,
                             'linewidth': 1,
                             'linecolor': line_rgb,
                             'mirror': True,
                             'tickfont': {'size': 16}
                             })
        # print('y_pos', y_pos)
        # print('t_pos', t_pos)
        for l in range(0, len(dids)):
            legend = 'legend'
            if l > 0:
                legend = legend + str(l+1)
            lgnd = {legend:{'yref': 'paper', 'y': y_pos[l], 'xref': 'paper', 'x': .01}}
            figure['layout'].update(lgnd)
            # print('title pos ', y_pos[l] + t_pos[l])
            figure['layout']['annotations'][l].update({'text': sub_plot_titles[l], 'x': .0375, 'font_size': 22, 'y': y_pos[l] + t_pos[l]})
            figure.add_annotation(
                xref='x domain',
                yref='y domain',
                xanchor='right',
                yanchor='bottom',
                x=1.0,
                y=-.246,
                font_size=18,
                text=sub_plot_bottom_titles[l],
                showarrow=False,
                row=(l+1), 
                col=1,
                bgcolor='rgba(255,255,255,.85)',
            )
        query = '?start_date=' + plot_start_date + '&end_date=' + plot_end_date + '&q=' + question_choice
        query = query + '&site_code=' + selected_platform + '&lat=' + str(selected_json['lat'])
        query = query + '&lon=' + str(selected_json['lon'])
    p4 = timeit.default_timer()
    # print('=-=-=-=-=-=-=-=-=-=-=-=-=  Finished plotting...')    
    # print('\tTotal time: ' + convertSeconds(p4-p0))
    # print('\t\tSet up, read platform: ' + convertSeconds(p1-p0))
    # print('\t\tSubplot setup: ' + convertSeconds(p2-p1))
    # print('\t\tRead data and plot: ' + convertSeconds(p3-p2))
    # print('\t\tSet plot options: ' + convertSeconds(p4 -p3))               
    return [row_style, plot_title, figure, list_group, query, '']


@app.callback(
    [
        Output('time-range-slider', 'value'),
        Output('start-date', 'value'),
        Output('end-date', 'value')
    ],
    [
        Input('time-range-slider', 'value'),
        Input('start-date', 'value'),
        Input('end-date', 'value'),
        Input('initial-time-start', 'data'),
        Input('initial-time-end', 'data')
    ], prevent_initial_call=True
)
def set_date_range_from_slider(slide_values, in_start_date, in_end_date, initial_start, initial_end):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == 'initial-time-start' or trigger_id == 'initial-time-end':
        start_output = initial_start
        end_output = initial_end
        try:
            in_start_date_obj = datetime.datetime.strptime(initial_start, d_format)
            start_seconds = in_start_date_obj.timestamp()
        except:
            start_seconds = all_start_seconds

        try:
            in_end_date_obj = datetime.datetime.strptime(initial_end, d_format)
            end_seconds = in_end_date_obj.timestamp()
        except:
            end_seconds = all_end_seconds

    else:
        if slide_values is None:
            raise dash.exceptions.PreventUpdate

        range_min = all_start_seconds
        range_max = all_end_seconds

        ctx = dash.callback_context
        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        start_seconds = slide_values[0]
        end_seconds = slide_values[1]

        start_output = in_start_date
        end_output = in_end_date

        if trigger_id == 'start-date':
            try:
                in_start_date_obj = datetime.datetime.strptime(in_start_date, d_format)
            except:
                in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
            start_output = in_start_date_obj.date().strftime(d_format)
            start_seconds = in_start_date_obj.timestamp()
            if start_seconds < range_min:
                start_seconds = range_min
                in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
                start_output = in_start_date_obj.date().strftime(d_format)
            elif start_seconds > range_max:
                start_seconds = range_max
                in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
                start_output = in_start_date_obj.date().strftime(d_format)
            elif start_seconds > end_seconds:
                start_seconds = end_seconds
                in_start_date_obj = datetime.datetime.fromtimestamp(start_seconds)
                start_output = in_start_date_obj.date().strftime(d_format)
        elif trigger_id == 'end-date':
            try:
                in_end_date_obj = datetime.datetime.strptime(in_end_date, d_format)
            except:
                in_end_date_obj = datetime.datetime.fromtimestamp((end_seconds))
            end_output = in_end_date_obj.date().strftime(d_format)
            end_seconds = in_end_date_obj.timestamp()
            if end_seconds < range_min:
                end_seconds = range_min
                in_end_date_obj = datetime.datetime.fromtimestamp(end_seconds)
                end_output = in_end_date_obj.date().strftime(d_format)
            elif end_seconds > range_max:
                end_seconds = range_max
                in_end_date_obj = datetime.datetime.fromtimestamp(end_seconds)
                end_output = in_end_date_obj.date().strftime(d_format)
            elif end_seconds < start_seconds:
                end_seconds = start_seconds
                in_end_date_obj = datetime.datetime.fromtimestamp(end_seconds)
                end_output = in_end_date_obj.date().strftime(d_format)
        elif trigger_id == 'time-range-slider':
            in_start_date_obj = datetime.datetime.fromtimestamp(slide_values[0])
            start_output = in_start_date_obj.strftime(d_format)
            in_end_date_obj = datetime.datetime.fromtimestamp(slide_values[1])
            end_output = in_end_date_obj.strftime(d_format)

    return [[start_seconds, end_seconds],
            start_output,
            end_output
            ]


if __name__ == '__main__':
    app.run_server(debug=True)
