import datetime

import dash
from dash import Dash, callback, html, dcc, dash_table, Input, Output, State, MATCH, ALL
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

url_years = 'https://data.pmel.noaa.gov/generic/erddap/tabledap/NTAS_flux.csv?TA_H,time,latitude,longitude,wmo_platform_code&orderByClosest(%22time/48hours%22)&time>=2001-03-31&time<=2004-06-12&wmo_platform_code="48401.0"&depth=5.7'
url_months = 'https://data.pmel.noaa.gov/generic/erddap/tabledap/NTAS_flux.csv?TA_H,time,latitude,longitude,wmo_platform_code&orderByClosest(%22time/24hours%22)&time>=2011-09-25&time<=2012-03-12&wmo_platform_code="48401.0"&depth=5.7'
url_days = 'https://data.pmel.noaa.gov/generic/erddap/tabledap/NTAS_flux.csv?TA_H,time,latitude,longitude,wmo_platform_code&orderByClosest(%22time/3hours%22)&time>=2009-06-04&time<=2009-07-12&wmo_platform_code="48401.0"&depth=5.7'
url_year_to_days = 'https://data.pmel.noaa.gov/generic/erddap/tabledap/NTAS_flux.csv?TA_H,time,latitude,longitude,wmo_platform_code&orderByClosest(%22time/3hours%22)&time>=2001-06-04&time<=2005-07-12&wmo_platform_code="48401.0"&depth=5.7'
app = dash.Dash(__name__)

one_day = 24*60*60*1000
a_yearish = one_day*365.25
for_year = '%Y'
for_day = '%e\n%b-%Y'
for_mon = "%b\n%Y"

app.layout = html.Div(children=[
    html.H4('Help with Ticks'),
    dcc.Graph(id='year-ticks'),
    dcc.Graph(id='mon-ticks'),
    dcc.Graph(id='day-ticks'),
    dcc.Graph(id='dynamic-ticks'),
    html.Div(id='no-show', style={'display': 'none'})
    ]
)


@app.callback(
    [
        Output('year-ticks', 'figure'),
        Output('mon-ticks', 'figure'),
        Output('day-ticks', 'figure'),
        Output('dynamic-ticks', 'figure')
    ],
    [
        Input('no-show', 'children'),
    ],
)
def make_plots(lets_go):
    ydf = pd.read_csv(url_years, skiprows=[1])
    ydf.loc[:, 'text_time'] = ydf['time'].astype(str)
    ydf.loc[:, 'time'] = pd.to_datetime(ydf['time'])
    ydf['text'] = ydf['text_time'] + '<br>' + ydf['TA_H'].astype(str)
    y_start_on_year = datetime.datetime.fromtimestamp(ydf['time'].iloc[0].timestamp()).replace(month=1, day=1, hour=0).isoformat()
    plot1 = go.Figure(go.Scattergl(
        x=ydf['time'],
        y=ydf['TA_H'],
        text=ydf['text'],
        hoverinfo='text',
        connectgaps=False,
        name='TA_H',
        marker={'color': 'black', },
        mode='lines+markers',
        showlegend=False,
    ))
    plot1.update_xaxes({
        'tick0': y_start_on_year,
        'dtick': a_yearish,
        'tickformat': for_year,
        'ticklabelmode': 'period',
        'showticklabels': True,
        'zeroline': True,
    })

    mdf = pd.read_csv(url_months, skiprows=[1])
    mdf.loc[:, 'text_time'] = mdf['time'].astype(str)
    mdf.loc[:, 'time'] = pd.to_datetime(mdf['time'])
    mdf['text'] = mdf['text_time'] + '<br>' + mdf['TA_H'].astype(str)
    m_start_on_year = datetime.datetime.fromtimestamp(mdf['time'].iloc[0].timestamp()).replace(month=1, day=1, hour=0).isoformat()
    plot2 = go.Figure(go.Scattergl(
        x=mdf['time'],
        y=mdf['TA_H'],
        text=mdf['text'],
        hoverinfo='text',
        connectgaps=False,
        name='TA_H',
        marker={'color': 'black', },
        mode='lines+markers',
        showlegend=False,
    ))
    plot2.update_xaxes({
        'tick0': m_start_on_year,
        'dtick': 'M1',
        'tickformat': for_mon,
        'ticklabelmode': 'period',
        'showticklabels': True,
        'zeroline': True,
    })

    ddf = pd.read_csv(url_days, skiprows=[1])
    ddf.loc[:, 'text_time'] = ddf['time'].astype(str)
    ddf.loc[:, 'time'] = pd.to_datetime(ddf['time'])
    ddf['text'] = ddf['text_time'] + '<br>' + ddf['TA_H'].astype(str)
    d_start_on_month = datetime.datetime.fromtimestamp(ddf['time'].iloc[0].timestamp()).replace(day=1, hour=0).isoformat()
    plot3 = go.Figure(go.Scattergl(
        x=ddf['time'],
        y=ddf['TA_H'],
        text=ddf['text'],
        hoverinfo='text',
        connectgaps=False,
        name='TA_H',
        marker={'color': 'black', },
        mode='lines+markers',
        showlegend=False,
    ))
    plot3.update_xaxes({
        'tick0': d_start_on_month,
        'dtick': one_day,
        'tickformat': for_day,
        'ticklabelmode': 'period',
        'showticklabels': True,
        'zeroline': True,
    })

    format_hints = [
        dict(dtickrange=[None, one_day], value="%H:%M\n%e-%b-%Y hint=1"),
        dict(dtickrange=[one_day, one_day*90], value="%e\n%b-%Y hint=2"),
        dict(dtickrange=[one_day*90, one_day*365*2], value="%b\n%Y hint=3"),
        dict(dtickrange=[one_day*365*2, one_day*365*100], value="%Y hint=4"),
    ]

    yddf = pd.read_csv(url_year_to_days, skiprows=[1])
    yddf.loc[:, 'time'] = pd.to_datetime(yddf['time'])
    yddf.loc[:, 'text_time'] = yddf['time'].astype(str)
    yddf['text'] = yddf['text_time'] + '<br>' + yddf['TA_H'].astype(str)
    print('hint3 min= ' + str(one_day*90))
    print('hint3 max=' + str(one_day*365*2))
    interval = yddf['time'].iloc[-1].timestamp()*1000 - yddf['time'].iloc[0].timestamp()*1000
    print('time range in millis=' + str(interval))
    plot4 = go.Figure(go.Scattergl(
        x=yddf['time'],
        y=yddf['TA_H'],
        text=yddf['text'],
        hoverinfo='text',
        connectgaps=False,
        name='TA_H',
        marker={'color': 'black', },
        mode='lines',
        showlegend=False,
    ))
    plot4.update_xaxes({
        'tickformatstops': format_hints,
        'ticklabelmode': 'period',
        'showticklabels': True,
        'zeroline': True,
    })

    return [plot1, plot2, plot3, plot4]


if __name__ == '__main__':
    app.run_server(debug=True)