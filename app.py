# Dash
from dash import (
    dash,
    Dash,
    callback,
    html,
    dcc,
    dash_table,
    Input,
    Output,
    State,
    MATCH,
    ALL,
    CeleryManager,
    DiskcacheManager,
    ctx,
    exceptions,
)
import dash_ag_grid as dag
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import dash_design_kit as ddk

# pytyony stuff
import os
import sys
import timeit
from urllib.parse import quote

# Standard tools and utilities
import pandas as pd
import json
import pprint
import numpy as np
import datetime
import flask
import urllib

import diskcache
import constants

import celery
from celery import Celery
from celery.schedules import crontab

# My stuff
from sdig.erddap.info import Info
import theme

dag.AgGrid(
    dashGridOptions={"suppressColumnVirtualisation": True}
)

version = "v3.1"  # new layout with ddk
empty_color = "#AAAAAA"
has_data_color = "black"

month_step = 60 * 60 * 24 * 30.25
d_format = "%Y-%m-%d"

height_of_row = 450
legend_gap = height_of_row
line_rgb = "rgba(.04,.04,.04,.2)"
plot_bg = "rgba(1.0, 1.0, 1.0 ,1.0)"

sub_sample_limit = 88000

y_pos_1_4 = [0.999, 0.73225, 0.447, 0.161]
t_pos_1_4 = [0.0005, 0.0005, 0.018, 0.036]
x_pos_1_4 = [0.1, 0.01, 0.01, 0.01]

y_pos_2 = [0.999, 0.3792]
t_pos_2 = [0.0005, 0.048]
x_pos_2 = [0.095, 0.011]

discover_error = """
You must configure a DISDOVERY_JSON env variable pointing to the JSON file that defines the which collections
of variables are to be in the discovery radio button list.
"""

graph_config = {
    "displaylogo": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
    "doubleClick": "reset+autosize",
    "toImageButtonOptions": {
        "height": None,
        "width": None,
    },
}

# platform_file = os.getenv('PLATFORM_JSON')
platform_file = "oceansites_flux_list.json"
if platform_file is None:
    platform_file = os.getenv("PLATFORMS_JSON")

pp = pprint.PrettyPrinter(indent=4)

ESRI_API_KEY = os.environ.get("ESRI_API_KEY")

discovery_file = "flux_discovery.json"
if discovery_file is None:
    discovery_file = os.getenv("DISCOVERY_FILE")

if discovery_file is not None:
    with open(discovery_file) as discovery_stream:
        discover_json = json.load(discovery_stream)
else:
    print("No config information found")
    sys.exit(-1)

radio_options = []
for key in discover_json["discovery"]:
    q = discover_json["discovery"][key]
    radio_options.append({"label": q["question"], "value": key})


all_start = None
all_end = None
all_start_seconds = 999999999999999
all_end_seconds = -999999999999999

with constants.postgres_engine.connect() as conn:
    times = pd.read_sql(
        f"SELECT MIN(start_date_seconds) as mins, MAX(end_date_seconds) maxs, MIN(start_date) as mind, MAX(end_date) as maxd from metadata",
        con=conn,
    )

all_start_seconds = times["mins"].values[0]
all_end_seconds = times["maxs"].values[0]
time_marks = Info.get_time_marks(all_start_seconds, all_end_seconds)

all_start = times["mind"].values[0]
all_end = times["maxd"].values[0]

control_label_style = {"font-size": "1.3em", "font-weight": "bold"}

celery_app = Celery(
    broker=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"),
    backend=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"),
)
if os.environ.get("DASH_ENTERPRISE_ENV") == "WORKSPACE":
    # For testing...
    # import diskcache
    cache = diskcache.Cache("./cache")
    background_callback_manager = DiskcacheManager(cache)
else:
    # For production...
    background_callback_manager = CeleryManager(celery_app)

color_discrete_map={
    "TAUX": "#636EFA",  # plotly graph obejcts default discrete colors [0] blue-ish 
    "TAUY": "#EF553B",  # plotly graph objects default discrete colors [1] red-ish
    'QNET': '#636EFA', 
    'QLAT': '#636EFA', 
    'QSEN': '#EF553B', 
    'RAIN':'#636EFA', 
    'EVAP': '#EF553B', 
    'QL':'#636EFA', 
    'QS': '#EF553B', 
    'QN': '#636EFA'
}


def get_blank(message):

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
                "font": {"size": 14},
            },
        ],
    )
    return blank_graph

app = dash.Dash(
    __name__,
    background_callback_manager=background_callback_manager,
)

app._favicon = "favicon.ico"
app.title = "Flux"
server = app.server

app.layout = ddk.App(theme=theme.theme,
    children=[
        dcc.Location(id="location", refresh=False),
        dcc.Store(id="active-platforms"),
        dcc.Store(id="inactive-platforms"),
        dcc.Store(id="selected-platform"),
        dcc.Store(id="map-info"),
        dcc.Store(id="initial-time-start"),  # time from initial load query string
        dcc.Store(id="initial-time-end"),  # time from initial load query string
        dcc.Store(id="initial-site"),  # A site coming in on the query string
        html.Div(id="data-div", style={"display": "none"}),
        ddk.Header(
            [
                ddk.Logo(app.get_asset_url("os_logo.gif")),
                ddk.Title("Flux Data Discovery"),

            ]
        ),
        ddk.Card(
            width=0.3,
            children=[
            
                ddk.Modal(hide_target=True, target_id='download-card', width='1060px', height='380', children=[
                    dcc.Loading(html.Button("Download Data", id='download-button', disabled=True))
                ]),
                ddk.ControlCard(
                    width=1.0,
                    children=[
                        ddk.ControlItem(
                            width=1.0,
                            label="Discover:",
                            label_style=control_label_style,
                            children=[
                                dcc.RadioItems(
                                    options=radio_options,
                                    id="radio-items",
                                ),
                            ],
                        ),
                    ],
                ),
                ddk.Card(children=[
                    ddk.Block(width=.5, children=[
                        dcc.Input(id='start-date', debounce=True, value=all_start),
                    ]),
                    ddk.Block(width=.5, children=[
                        dcc.Input(id='end-date', debounce=True, value=all_end),
                    ]),
                    html.Div(style={'padding-right': '40px', 'padding-left': '40px', 'padding-top': '20px', 'padding-bottom': '45px'}, children=[
                            dcc.RangeSlider(id='time-range-slider',
                                            value=[all_start_seconds, all_end_seconds],
                                            min=all_start_seconds,
                                            max=all_end_seconds,
                                            step=month_step,
                                            marks=time_marks,
                                            updatemode='mouseup',
                                            allowCross=False)
                    ])
                ]),
            ]),
        ddk.Block(width=.7, children=[
            ddk.Card(children=[
                ddk.CardHeader(children=['Select the type of data and date range. Black dots have data, gray dots do not.',
                    dcc.Loading(html.Div(id='map-loading',style={'padding-right': '40px'}))
                ]),
                ddk.Graph(id='location-map', config=graph_config),
            ])
        ]),
        ddk.Block(width=1.0, children=[
            ddk.Card(children=[
                ddk.CardHeader(id='plot-card-title', children='Make selections for data and time range, then click a platform loction'),
                dcc.Loading(
                    ddk.Graph(id='plot-graph', config=graph_config, figure=get_blank('Select data and time range to search.'))
                ) 
            ])
        ]),
        ddk.Card(style={'margin-bottom': '10px'}, children=[
        ddk.Block(children=[
            ddk.Block(width=.08, children=[
                html.Img(src='https://www.pmel.noaa.gov/sites/default/files/PMEL-meatball-logo-sm.png',
                            height=100,
                            width=100),
            ]),
            ddk.Block(width=.83, children=[
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
                    dcc.Link('DOC |', href='https://www.commerce.gov/', target='_blank'),
                    dcc.Link(' NOAA |', href='https://www.noaa.gov/', target='_blank'),
                    dcc.Link(' OAR |', href='https://www.research.noaa.gov/', target='_blank'),
                    dcc.Link(' PMEL |', href='https://www.pmel.noaa.gov/', target='_blank'),
                    dcc.Link(' Privacy Policy |', href='https://www.noaa.gov/disclaimer', target='_blank'),
                    dcc.Link(' Disclaimer |', href='https://www.noaa.gov/disclaimer', target='_blank'),
                    dcc.Link(' Accessibility |', href='https://www.pmel.noaa.gov/accessibility', target='_blank'),
                    dcc.Link( version, href='https://github.com/NOAA-PMEL/lts', target='_blank')
                ])
            ]),
        ]),
    ]),
    ddk.Card(id='download-card', children=[
        ddk.CardHeader('Download the data at full resolution:'),
        dag.AgGrid(
            style={'height': 250},
            id="download-grid",
            defaultColDef={"cellRenderer": "markdown"},
            columnDefs=[
                {'field': 'title', 'headerName':"Dataset", 'width': '550'},
                {'field': 'html', "linkTarget":"_blank", 'headerName': 'HTML', 
                    'width': 100,
                    "cellStyle": {
                        "color": "rgb(31, 120, 180)",
                        "text-decoration": "underline",
                        "cursor": "pointer",
                    },
                },
                {'field': 'csv', "linkTarget":"_blank", 'headerName': 'CSV',
                    'width': 100,
                    "cellStyle": {
                        "color": "rgb(31, 120, 180)",
                        "text-decoration": "underline",
                        "cursor": "pointer",
                    },
                },
                {'field': 'netcdf', "linkTarget":"_blank", 'headerName': 'NetCDF',
                    'width': 100,
                    "cellStyle": {
                        "color": "rgb(31, 120, 180)",
                        "text-decoration": "underline",
                        "cursor": "pointer",
                    },
                },
                {'field': 'erddap', "linkTarget":"_blank", 'headerName': 'ERDDAP',
                    'width': 160,
                    "cellStyle": {
                        "color": "rgb(31, 120, 180)",
                        "text-decoration": "underline",
                        "cursor": "pointer",
                    },
                },
            ],
        ),
    ])
])


def make_gaps(pdf, fre):
    if pdf.shape[0] > 3:
        # This magic inserts missing values between rows that are more than two deltas apart.
        # Make time the index to the data
        pdf2 = pdf.set_index("time")
        pdf2 = pdf2[~pdf2.index.duplicated()]
        # make a index at the expected delta
        fill_dates = pd.date_range(pdf["time"].iloc[0], pdf["time"].iloc[-1], freq=fre)
        # sprinkle the actual values out along the new time axis, by combining the regular
        # intervals index and the data index
        all_dates = fill_dates.append(pdf2.index)
        all_dates = all_dates[~all_dates.duplicated()]
        fill_sort = sorted(all_dates)
        # reindex the data which causes NaNs everywhere in the regular index that don't
        # exactly match the data, with the data in between the NaNs
        pdf3 = pdf2.reindex(fill_sort)
        # remove the NaN rows that are by themselves because there is data near enough
        mask1 = ~pdf3["site_code"].notna() & ~pdf3["site_code"].shift().notna()
        mask2 = pdf3["site_code"].notna()
        pdf4 = pdf3[mask1 | mask2]
        # Reindex to 0 ... N
        pdf = pdf4.reset_index()
    return pdf


@app.callback(
    [
        Output("initial-time-start", "data"),
        Output("initial-time-end", "data"),
        Output("radio-items", "value"),
        Output("initial-site", "data"),
    ],
    [Input("data-div", "n_clicks")],
    [State("location", "search")],
)
def process_query(aclick, qstring):
    qurl = flask.request.referrer
    parts = urllib.parse.urlparse(qurl)
    params = urllib.parse.parse_qs(parts.query)
    # get defaults from initial load
    initial_start_time = all_start
    initial_end_time = all_end
    dq = ""
    if "start_date" in params:
        initial_start_time = params["start_date"][0]
    if "end_date" in params:
        initial_end_time = params["end_date"][0]
    if "q" in params:
        dq = params["q"][0]
    initial_site_json = {}
    if "site_code" in params and "lat" in params and "lon" in params:
        initial_site_code = params["site_code"][0]
        initial_lat = params["lat"][0]
        initial_lon = params["lon"][0]
        initial_site_json = {
            "site_code": initial_site_code,
            "lat": initial_lat,
            "lon": initial_lon,
        }
    return [initial_start_time, initial_end_time, dq, json.dumps(initial_site_json)]



@app.callback([Output("map-info", "data")], [Input("location-map", "relayoutData")])
def record_map_change(relay_data):
    center = {"lon": 0.0, "lat": 0.0}
    zoom = 1.4
    if relay_data is not None:
        if "map.center" in relay_data:
            center = relay_data["map.center"]
        if "map.zoom" in relay_data:
            zoom = relay_data["map.zoom"]
    map_info = {"center": center, "zoom": zoom}
    return [json.dumps(map_info)]


@app.callback(
    [
        Output("active-platforms", "data"),
        Output("inactive-platforms", "data"),
        Output("map-loading", "children"),
    ],
    [
        Input("start-date", "value"),
        Input("end-date", "value"),
        Input("radio-items", "value"),
    ],
    prevent_initial_call=True,
)
def update_platform_state(in_start_date, in_end_date, in_data_question):
    time0 = timeit.default_timer()
    time_constraint = ""
    all_with_data = None
    all_without_data = None
    # check to see which platforms have data for the current variables
    if in_start_date is not None and in_end_date is not None:
        n_start_obj = datetime.datetime.strptime(in_start_date, d_format)
        n_start_obj.replace(day=1, hour=0)
        time_constraint = time_constraint + "time>='" + n_start_obj.isoformat() + "'"

        n_end_obj = datetime.datetime.strptime(in_end_date, d_format)
        n_end_obj.replace(day=1, hour=0)
        time_constraint = time_constraint + " AND time<='" + n_end_obj.isoformat() + "'"
        if n_start_obj.year != n_end_obj.year:
            count_by = "1year"
        elif (
            n_start_obj.year == n_end_obj.year and n_start_obj.month != n_end_obj.month
        ):
            count_by = "1month"
        else:
            count_by = "1day"
    time1 = timeit.default_timer()
    if in_data_question is not None and len(in_data_question) > 0:
        for qin in discover_json["discovery"]:
            if qin == in_data_question:
                search_params = discover_json["discovery"][qin]["search"]
                for search in search_params:
                    vars_to_get = ['"' + short + '"' for short in search["short_names"]]
                    read_dtypes = {}
                    for short in search["short_names"]:
                        read_dtypes[short] = np.float64
                    vars_to_get.append("time")
                    vars_to_get.append("site_code")
                    join_type = search["join"]
                    locations_to_map = None
                    with constants.postgres_engine.connect() as conn:
                        locations_to_map = pd.read_sql(
                            f"SELECT * from locations", con=conn
                        )
                    var_list = ",".join(vars_to_get)
                    with constants.postgres_engine.connect() as conn:
                        have = pd.read_sql(
                            f"SELECT {var_list} FROM nobs WHERE {time_constraint}",
                            con=conn,
                            dtype=read_dtypes,
                        )
                    if have is not None:
                        csum = have.groupby(["site_code"]).sum().reset_index()
                        csum["site_code"] = csum["site_code"].astype(str)
                        sum_n = None
                        if join_type == "or":
                            csum["has_data"] = csum[search["short_names"]].sum(axis=1)
                            csum = csum.sort_values("site_code")
                            locations_to_map = locations_to_map.sort_values("site_code")
                            sum_n = csum.loc[csum["has_data"] > 0]
                        if join_type == "and":
                            chk_vars = search["short_names"]
                            criteria = ""
                            for vix, v in enumerate(chk_vars):
                                if vix > 0:
                                    criteria = criteria + " & "
                                criteria = criteria + "(csum['" + v + "']" + " > 0)"
                            criteria = "csum[(" + criteria + ")]"
                            # eval dereferences all the stuff in the string and runs it
                            sum_n = pd.eval(criteria)
                        # DEBUG print('sum of counts')
                        # DEBUG print(sum_n)
                        if sum_n is not None and sum_n.shape[0] > 0:
                            # sum_n is the platforms that have data.
                            # This merge operation (as explained here:
                            # https://stackoverflow.com/questions/53645882/pandas-merging-101/53645883#53645883)
                            # combines the locations data frame with
                            # the information about which sites have observations to make something
                            # that can be plotted.
                            some_data = locations_to_map.merge(
                                sum_n, on="site_code", how="inner"
                            )
                            some_data["platform_color"] = has_data_color
                            if all_with_data is None:
                                all_with_data = some_data
                            else:
                                all_with_data = pd.concat([all_with_data, some_data])
                            criteria = (
                                locations_to_map.site_code.isin(some_data.site_code)
                                == False
                            )
                            no_data = locations_to_map.loc[criteria].reset_index()
                            no_data["platform_color"] = empty_color
                            if all_without_data is None:
                                all_without_data = no_data
                            else:
                                all_without_data = pd.concat(
                                    [all_without_data, no_data]
                                )
                    else:
                        locations_to_map["platform_color"] = empty_color
                        if all_without_data is None:
                            all_without_data = locations_to_map
                        else:
                            all_without_data = pd.concat(
                                [all_without_data, locations_to_map]
                            )
    else:
        # Everything is empty at the start
        with constants.postgres_engine.connect() as conn:
            all_without_data = pd.read_sql(f"SELECT * from locations", con=conn)
        all_without_data["platform_color"] = empty_color

    locations_with_data = json.dumps(
        pd.DataFrame(
            columns=["latitude", "longitude", "site_code", "platform_color"],
            index=[0],
        ).to_json()
    )
    locations_without_data = json.dumps(
        pd.DataFrame(
            columns=["latitude", "longitude", "site_code", "platform_color"],
            index=[0],
        ).to_json()
    )
    time2 = timeit.default_timer()
    if all_with_data is not None:
        all_with_data.reset_index(inplace=True, drop=True)
        # DEBUG print('saving non-empty data:', all_with_data)
        locations_with_data = json.dumps(all_with_data.to_json())
    if all_without_data is not None:
        all_without_data.reset_index(inplace=True, drop=True)
        locations_without_data = json.dumps(all_without_data.to_json())
    time3 = timeit.default_timer()
    # print('Total time: ' + convertSeconds(time3-time0))
    # print('\tSetup dates: ' + convertSeconds(time1-time0))
    # print('\tRead counts ERDDAP: ' + convertSeconds(time2-time1))
    # print('\tReset Indexes: ' + convertSeconds(time3-time2))
    return [locations_with_data, locations_without_data, ""]


def convertSeconds(in_seconds):
    seconds = int(in_seconds) % 60
    minutes = int(in_seconds / (60)) % 60
    hours = int(in_seconds / (60 * 60)) % 24
    return str(hours) + ":" + str(minutes) + ":" + str(seconds)


@app.callback(
    [
        Output("location-map", "figure"),
    ],
    [
        Input("active-platforms", "data"),
        Input("inactive-platforms", "data"),
        Input("selected-platform", "data"),
    ],
    [State("map-info", "data")],
    prevent_initial_call=True,
)
def make_location_map(
    in_active_platforms, in_inactive_platforms, in_selected_platform, in_map
):
    tp0 = timeit.default_timer()
    center = {"lon": 0.0, "lat": 0.0}
    zoom = 1.4
    if in_map is not None:
        map_inf = json.loads(in_map)
        center = map_inf["center"]
        zoom = map_inf["zoom"]
    location_map = go.Figure()
    selected_plat = None
    tp1 = timeit.default_timer()
    if in_selected_platform is not None:
        selected_plat = json.loads(in_selected_platform)
    tp2 = timeit.default_timer()
    if in_active_platforms is not None and in_inactive_platforms is not None:
        data_for_yes = pd.read_json(json.loads(in_active_platforms))
        # DEBUG print(data_for_yes)
        data_for_no = pd.read_json(json.loads(in_inactive_platforms))
        no_trace = None
        if data_for_no.shape[0] > 0:
            no_trace = go.Scattermap(
                lat=data_for_no["latitude"],
                lon=data_for_no["longitude"],
                hovertext=data_for_no["site_code"],
                hoverinfo="lat+lon+text",
                customdata=data_for_no["site_code"],
                marker={"color": data_for_no["platform_color"], "size": 10},
                mode="markers",
            )
        yes_trace = None
        if data_for_yes.shape[0] > 0:
            yes_trace = go.Scattermap(
                lat=data_for_yes["latitude"],
                lon=data_for_yes["longitude"],
                hovertext=data_for_yes["site_code"],
                hoverinfo="lat+lon+text",
                customdata=data_for_yes["site_code"],
                marker={"color": data_for_yes["platform_color"], "size": 10},
                mode="markers",
            )
        if no_trace is not None:
            location_map.add_trace(no_trace)
        if yes_trace is not None:
            location_map.add_trace(yes_trace)

    tp3 = timeit.default_timer()
    if (
        selected_plat is not None
        and "lat" in selected_plat
        and "lon" in selected_plat
        and "site_code" in selected_plat
    ):
        yellow_trace = go.Scattermap(
            lat=[selected_plat["lat"]],
            lon=[selected_plat["lon"]],
            hovertext=[selected_plat["site_code"]],
            hoverinfo="lat+lon+text",
            customdata=[selected_plat["site_code"]],
            marker={"color": "yellow", "size": 15},
            mode="markers",
        )
        location_map.add_trace(yellow_trace)
    tp4 = timeit.default_timer()
    location_map.update_layout(
        showlegend=False,
        map_style="white-bg",
        map_layers=[
            {
                "below": "traces",
                "sourcetype": "raster",
                "sourceattribution": "&nbsp;GEBCO &amp; NCEI&nbsp;",
                "source": [
                    "https://tiles.arcgis.com/tiles/C8EMgrsFcRFL6LrL/arcgis/rest/services/GEBCO_basemap_NCEI/MapServer/tile/{z}/{y}/{x}"
                ],
            }
        ],
        map_zoom=zoom,
        map_center=center,
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        legend=dict(
            orientation="v",
            x=-0.01,
        ),
        modebar_orientation="v",
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
        Output("selected-platform", "data"),
    ],
    [Input("location-map", "clickData"), Input("initial-site", "data")],
    prevent_initial_call=True,
)
def update_selected_platform(click, initial_site):
    selection = None
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == "initial-site":
        selection = initial_site
    else:
        if click is not None:
            if "points" in click:
                point_dict = click["points"][0]
                selected_platform = point_dict["customdata"]
                selected_lat = point_dict["lat"]
                selected_lon = point_dict["lon"]
                selection = json.dumps(
                    {
                        "site_code": selected_platform,
                        "lat": selected_lat,
                        "lon": selected_lon,
                    }
                )
    return [selection]


@app.callback(
    [
        Output('download-button', 'disabled'),
        Output("plot-card-title", "children"),
        Output("plot-graph", "figure"),
        Output("download-grid", "rowData"),
        Output("location", "search"),
    ],
    [
        Input("selected-platform", "data"),
        Input("start-date", "value"),
        Input("end-date", "value"),
        Input("active-platforms", "data"),
    ],
    [
        State("radio-items", "value"),
    ],
    prevent_initial_call=True,
    background=True,
)
def plot_from_selected_platform(
    selection_data,
    plot_start_date,
    plot_end_date,
    active_platforms,
    question_choice,
):

    if selection_data is not None:
        selected_json = json.loads(selection_data)
        if "site_code" in selected_json:
            selected_platform = selected_json["site_code"]
        else:
            raise exceptions.PreventUpdate
    else:
        raise exceptions.PreventUpdate
    if (
        plot_start_date is not None
        and len(plot_start_date) > 0
        and plot_end_date is not None
        and len(plot_end_date) > 0
    ):
        plot_time = "&time>=" + plot_start_date + "&time<=" + plot_end_date
    else:
        raise exceptions.PreventUpdate

    with constants.postgres_engine.connect() as conn:
        plots_df = pd.read_sql(
            f"SELECT * from discovery WHERE site_code='{selected_platform}' AND question_id='{question_choice}' ORDER BY did",
            con=conn,
        )
    
    p0 = timeit.default_timer()
    
    download_grid = []

    p1 = timeit.default_timer()
    if selected_platform is not None:

        if plots_df.empty:
            message = (
                "No data available at "
                + selected_platform
                + " for "
                + plot_start_date
                + " to "
                + plot_end_date
            )
            return [
                True,
                "",
                get_blank(message),
                download_grid,
                "",
            ]
        # Get list of datasets which contain these site codes for this question
        num_rows = plots_df.shape[0]

        to_plot = plots_df.to_dict(orient="records")

        dids = list(plots_df["did"])

        figure = make_subplots(
            rows=num_rows,
            cols=1,
            row_heights=[450] * num_rows,
            shared_xaxes="all",
            shared_yaxes=False,
            subplot_titles=dids,
            vertical_spacing=(0.275 / num_rows),
        )
        dataset_idx = 0
        sub_plot_titles = []
        sub_plot_bottom_titles = []
        if len(dids) == 2:
            y_pos = y_pos_2.copy()
            t_pos = t_pos_2.copy()
            x_pos = x_pos_2.copy()
        else:
            y_pos = y_pos_1_4.copy()
            t_pos = t_pos_1_4.copy()
            x_pos = x_pos_1_4.copy()
        p2 = timeit.default_timer()
        

        for (
            dataset_idx,
            row,
        ) in enumerate(to_plot):  # it has at most four rows. Don't panic.
            grid_row = {}
            dataset_idx = dataset_idx + 1
            p_did = row["did"]
            with constants.postgres_engine.connect() as conn:
                current_dataset = pd.read_sql(
                    f"SELECT * from metadata where id='{p_did}'", con=conn
                )
                units = pd.read_sql(
                    f"SELECT * from units where did='{p_did}'", con=conn
                )
            p_url = str(current_dataset["url"].values[0])
            short_string = row["short_string"]
            pvars = short_string + ",site_code,time"
            p_url = (
                p_url
                + ".csv?"
                + pvars
                + plot_time
                + '&site_code="'
                + selected_platform
                + '"'
            )
            print("Making a plot of " + p_url)
            plot_title = "Plot of " + short_string + " at " + selected_platform
            df = pd.read_csv(p_url, skiprows=[1])
            sub_title = selected_platform
            bottom_title = current_dataset["title"].astype(str).values[0]
            if df.shape[0] > sub_sample_limit:
                df = df.sample(n=sub_sample_limit).sort_values("time")
                sub_title = (
                    sub_title
                    + " (timeseries sub-sampled to "
                    + str(sub_sample_limit)
                    + " points) "
                )
            sub_plot_titles.append(sub_title)
            sub_plot_bottom_titles.append(bottom_title)
            l_labels = []
            vlist = short_string.split(",")
            for n, v in enumerate(vlist):
                if v in units:
                    unit = units[v].astype(str).values[0]
                    l_labels.append(v + " (" + unit + ")")
                else:
                    l_labels.append(v)
            lines = px.line(df, x="time", y=vlist, labels=l_labels, color_discrete_map=color_discrete_map)
            legend_name = "legend"
            if dataset_idx > 1:
                legend_name = "legend" + str(dataset_idx)
            lines.update_traces(legend=legend_name)
            for ifig, fig in enumerate(list(lines.select_traces())):
                nfig = go.Figure(fig)
                nfig.update_traces(name=l_labels[ifig])
                figure.add_trace(list(nfig.select_traces())[0], row=dataset_idx, col=1)


            grid_row['title'] = current_dataset["title"].astype(str).values[0] + " at " + selected_platform
            grid_row['erddap'] = f'[ERDDAP Data Page]({current_dataset["url"].astype(str).values[0]})'
            grid_row['html'] = f'[HTML]({p_url.replace(".csv", ".htmlTable")})'
            grid_row['csv'] =  f'[CSV]({p_url.replace(".htmlTable", ".csv")})'
            grid_row['netcdf'] = f'[NetCDF]({p_url.replace(".csv", ".ncCF")})'
            download_grid.append(grid_row)
         
        p3 = timeit.default_timer()
        figure.update_layout(height=height_of_row * num_rows)
        figure.update_layout(
            plot_bgcolor=plot_bg,
            hovermode="x",
            paper_bgcolor="white",
            margin=dict(
                l=80,
                r=80,
                b=80,
                t=80,
            ),
        )
        figure.update_xaxes(
            {
                "ticklabelmode": "period",
                "showticklabels": True,
                "gridcolor": line_rgb,
                "zeroline": True,
                "zerolinecolor": line_rgb,
                "showline": True,
                "linewidth": 1,
                "linecolor": line_rgb,
                "mirror": True,
                "tickfont": {"size": 16},
                "tickformatstops": [
                    dict(dtickrange=[1000, 60000], value="%H:%M:%S\n%d%b%Y"),
                    dict(dtickrange=[60000, 3600000], value="%H:%M\n%d%b%Y"),
                    dict(dtickrange=[3600000, 86400000], value="%H:%M\n%d%b%Y"),
                    dict(dtickrange=[86400000, 604800000], value="%e\n%b %Y"),
                    dict(dtickrange=[604800000, "M1"], value="%b\n%Y"),
                    dict(dtickrange=["M1", "M12"], value="%b\n%Y"),
                    dict(dtickrange=["M12", None], value="%Y"),
                ],
            }
        )
        figure.update_yaxes(
            {
                "gridcolor": line_rgb,
                "zeroline": True,
                "zerolinecolor": line_rgb,
                "showline": True,
                "linewidth": 1,
                "linecolor": line_rgb,
                "mirror": True,
                "tickfont": {"size": 16},
            }
        )
        # print('y_pos', y_pos)
        # print('t_pos', t_pos)
        for l in range(0, len(dids)):
            legend = "legend"
            if l > 0:
                legend = legend + str(l + 1)
            lgnd = {
                legend: {
                    "yref": "paper",
                    "y": y_pos[l],
                    "xref": "paper",
                    "x": x_pos[l],
                    "orientation": "v",
                    "bgcolor": "white",
                }
            }
            figure["layout"].update(lgnd)
            # print('title pos ', y_pos[l] + t_pos[l])
            figure["layout"]["annotations"][l].update(
                {
                    "text": sub_plot_titles[l],
                    "x": 0.0375,
                    "font_size": 22,
                    "y": y_pos[l] + t_pos[l],
                }
            )
            figure.add_annotation(
                xref="x domain",
                yref="y domain",
                xanchor="right",
                yanchor="bottom",
                x=1.0,
                y=-0.246,
                font_size=22,
                text=sub_plot_bottom_titles[l],
                showarrow=False,
                row=(l + 1),
                col=1,
                bgcolor="rgba(255,255,255,.85)",
            )
        query = (
            "?start_date="
            + plot_start_date
            + "&end_date="
            + plot_end_date
            + "&q="
            + question_choice
        )
        query = (
            query
            + "&site_code="
            + selected_platform
            + "&lat="
            + str(selected_json["lat"])
        )
        query = query + "&lon=" + str(selected_json["lon"])
        p4 = timeit.default_timer()
        # print('=-=-=-=-=-=-=-=-=-=-=-=-=  Finished plotting...')
        # print('\tTotal time: ' + convertSeconds(p4-p0))
        # print('\t\tSet up, read platform: ' + convertSeconds(p1-p0))
        # print('\t\tSubplot setup: ' + convertSeconds(p2-p1))
        # print('\t\tRead data and plot: ' + convertSeconds(p3-p2))
        # print('\t\tSet plot options: ' + convertSeconds(p4 -p3))
        return [False, plot_title, figure, download_grid, query]


@app.callback(
    [
        Output("time-range-slider", "value"),
        Output("start-date", "value"),
        Output("end-date", "value"),
    ],
    [
        Input("time-range-slider", "value"),
        Input("start-date", "value"),
        Input("end-date", "value"),
        Input("initial-time-start", "data"),
        Input("initial-time-end", "data"),
    ],
    prevent_initial_call=True,
)
def set_date_range_from_slider(
    slide_values, in_start_date, in_end_date, initial_start, initial_end
):
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger_id == "initial-time-start" or trigger_id == "initial-time-end":
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
            raise exceptions.PreventUpdate

        range_min = all_start_seconds
        range_max = all_end_seconds

        trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]

        start_seconds = slide_values[0]
        end_seconds = slide_values[1]

        start_output = in_start_date
        end_output = in_end_date

        if trigger_id == "start-date":
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
        elif trigger_id == "end-date":
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
        elif trigger_id == "time-range-slider":
            in_start_date_obj = datetime.datetime.fromtimestamp(slide_values[0])
            start_output = in_start_date_obj.strftime(d_format)
            in_end_date_obj = datetime.datetime.fromtimestamp(slide_values[1])
            end_output = in_end_date_obj.strftime(d_format)

    return [[start_seconds, end_seconds], start_output, end_output]


if __name__ == "__main__":
    app.run(debug=True)
