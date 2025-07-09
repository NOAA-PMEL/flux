#### Air Sea Fluxes Data Discovery Dashboard

This is a Plotly Dash application which allows data discovery and plotting
data in the OceanSITES Air-Sea fluxes collection. For a specified time periods,
users can use the interface to
find the answer to the question of which sites have:

- Wind Stress
- Net surface heat flux
- Turbulent heat flux
- Precipitation
- Evaporation minus precipitation

Selecting a station will plot the relevant parameters and provide a link to 
download the plotted data in a variety of formats.

#### To add an ERDDAP data set to this dashboard, follow these steps.

1. Add the ERDDAP URL to the section of the flux_discovery.json file that is appropriate for the way the variables are named in the the data set. You might have to add it to several sections since many data sets have variables from more than one of the discover questions.
1. Add a ERDDAP URL to the oceansites_flux_list.json. The first URL doesn't really get used so it will likely be removed in the future. The second URL should be a query that returns the location of the platform. The distinct is intended to get to only one value of lat and lon since these are "fixed" platforms. However, some data sets have slightly different lat and lons for each deployment that is included in the data set. In this case, the notebook below will create a mean location and use that.
1. Run all the cells in make_nobs_db.ipynb to recreate all the databases that drive the app to now inclue the data source you just added.

#### Legal Disclaimer
*This repository is a software product and is not official communication
of the National Oceanic and Atmospheric Administration (NOAA), or the
United States Department of Commerce (DOC).  All NOAA GitHub project
code is provided on an 'as is' basis and the user assumes responsibility
for its use.  Any claims against the DOC or DOC bureaus stemming from
the use of this GitHub project will be governed by all applicable Federal
law.  Any reference to specific commercial products, processes, or services
by service mark, trademark, manufacturer, or otherwise, does not constitute
or imply their endorsement, recommendation, or favoring by the DOC.
The DOC seal and logo, or the seal and logo of a DOC bureau, shall not
be used in any manner to imply endorsement of any commercial product
or activity by the DOC or the United States Government.*
