import datetime
import dateutil

import dash
from dash import Dash, callback, html, dcc, dash_table, Input, Output, State, MATCH, ALL
import pandas as pd
import plotly.graph_objects as go
import json

start_date = '2001-04-01'
# decade
end_date = '2010-03-31'
# year
# end_date = '2002-03-31'
# 15 days
# end_date = '2001-04-15'
# 3 days
# end_date = '2001-04-03T23:59'

url_year_to_days = 'https://data.pmel.noaa.gov/generic/erddap/tabledap/NTAS_flux.csv?TA_H,time,latitude,longitude,wmo_platform_code&time>='+start_date+'&time<='+end_date+'&wmo_platform_code="48401.0"&depth=5.7'

app = dash.Dash(__name__)

one_day = 24*60*60*1000
a_yearish = one_day*365.25
for_year = '%Y'
for_day = '%e\n%b-%Y'
for_mon = "%b\n%Y"

df = pd.read_csv(url_year_to_days, skiprows=[1])
df.loc[:, 'time'] = pd.to_datetime(df['time'])
df.loc[:, 'text_time'] = df['time'].astype(str)
df['text'] = df['text_time'] + '<br>' + df['TA_H'].apply(lambda x: '{0:.2f}'.format(x))
time_max = df['time'].iloc[-1].timestamp()
time_min = df['time'].iloc[0].timestamp()
data_range = time_max*1000 - time_min*1000

app.layout = html.Div(children=[
    html.H4('Dynamic Ticks'),
    dcc.Graph(id='dynamic-ticks'),
    html.Div(id='no-show', style={'display': 'none'}),
    dcc.Store('tick-data')
    ]
)


@app.callback(
    [
        Output('tick-data', 'data')
    ],
    [
        Input('dynamic-ticks', 'relayoutData'),
    ]
)
def write_tick_data(relay_data):
    if relay_data is not None:
        if 'xaxis.range[0]' in relay_data and 'xaxis.range[1]' in relay_data:
            print('zooming in:', datetime.datetime.now().isoformat())
            in_time_min = dateutil.parser.parse(relay_data['xaxis.range[0]'])
            in_time_max = dateutil.parser.parse(relay_data['xaxis.range[1]'])
            ticks = get_ticks(in_time_min.timestamp(), in_time_max.timestamp())
            return [json.dumps(ticks)]
        elif 'xaxis.autorange' in relay_data:
            print('resetting zoom to original:', datetime.datetime.now().isoformat())
            ticks = get_ticks(time_min, time_max)
            return [json.dumps(ticks)]
        else:
            raise dash.exceptions.PreventUpdate
    else:
        raise dash.exceptions.PreventUpdate

@app.callback(
    [
        Output('dynamic-ticks', 'figure'),
    ],
    [
        Input('no-show', 'children'),
        Input('tick-data', 'data')
    ],
    [
        State('dynamic-ticks', 'figure'),
    ]
)
def make_plots(lets_go, tick_data, current_figure):

    if current_figure is not None and tick_data is not None:
        ticks = json.loads(tick_data)
        fig = go.Figure(data=current_figure['data'], layout=current_figure['layout'])
        fig.update_xaxes(
            {
                'tick0': ticks['tick0'],
                'dtick': ticks['dtick'],
                'tickformat': ticks['tickformat']
            }
        )
        return [fig]

    ticks = get_ticks(time_min, time_max)

    plot = go.Figure(go.Scattergl(
        x=df['time'],
        y=df['TA_H'],
        text=df['text'],
        hoverinfo='text',
        connectgaps=False,
        name='TA_H',
        marker={'color': 'black', },
        mode='lines',
        showlegend=False,
    ))
    plot.update_xaxes(ticks)
    plot.update_xaxes({
        'ticklabelmode': 'period',
        'showticklabels': True,
        'zeroline': True,
    })

    return [plot]


def get_ticks(time_min, time_max):
    interval = time_max*1000 - time_min*1000
    if interval <= one_day:
        dtick = 60*60*1000  # one hour
        dtickformat = "%H:%M\n%e-%b-%Y"
        tick0 = datetime.datetime.fromtimestamp(time_min).replace(hour=0, minute=0).isoformat()
    elif one_day < interval <= one_day*45:
        dtick = one_day
        dtickformat = "%e\n%b-%Y"
        tick0 = datetime.datetime.fromtimestamp(time_min).replace(day=1, hour=0, minute=0).isoformat()
    elif one_day*45 < interval <= one_day*365.0*2:
        dtick = "M1"
        monthish = one_day*30.25
        dtickformat = "%b\n%Y"
        tick0 = datetime.datetime.fromtimestamp(time_min).replace(month=1, day=1, hour=0, minute=0).isoformat()
    else:
        dtick = one_day*365.0
        dtickformat = "%Y"
        print('dtick=', dtick)
        tick0 = datetime.datetime.fromtimestamp(time_min).replace(month=1, day=1, hour=0, minute=0).isoformat()
    return {'dtick': dtick, 'tickformat': dtickformat, 'tick0': tick0}


if __name__ == '__main__':
    app.run_server(debug=True)