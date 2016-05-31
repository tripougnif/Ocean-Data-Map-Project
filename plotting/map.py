from netCDF4 import Dataset, netcdftime
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.basemap import maskoceans
import numpy as np
import re
import colormap
import cStringIO
import basemap
import overlays
from data import load_interpolated


def plot(url, climate_url, **kwargs):
    query = kwargs.get('query')

    scale = query.get('scale')
    if scale is None or scale == 'auto':
        scale = None
    else:
        scale = [float(x) for x in scale.split(',')]

    variables = query.get('variable').split(',')
    vector = False
    if len(variables) > 1:
        vector = True
        # quivervars = quiver.split(",")

    # TODO: Make this work on multiple locations, with different projections
    if 'arctic' == query.get('location'):
        m = basemap.load_arctic()
    elif 'pacific' == query.get('location'):
        m = basemap.load_pacific()
    elif 'nwatlantic' == query.get('location'):
        m = basemap.load_nwatlantic()
    else:
        # Default to NW Atlantic
        m = basemap.load_nwatlantic()

    with Dataset(url, 'r') as dataset:
        if query.get('time') is None or len(query.get('time')) == 0:
            time = -1
        else:
            time = int(query.get('time'))

        if time >= dataset.variables['time_counter'].shape[0]:
            time = -1

        variable_unit = dataset.variables[variables[0]].units
        variable_name = dataset.variables[
            variables[0]].long_name.replace(" at CMC", "")
        if vector:
            variable_name = re.sub(r"(?i)( x | y |zonal |meridional )", " ",
                                   variable_name)
            variable_name = re.sub(r" +", " ", variable_name)

        anom = str(query.get('anomaly')).lower() in ['true', 'yes', 'on']
        if len(variables) > 1 or \
            ('votemper' not in variables and
                'vosaline' not in variables and
                'bottom_votemper' not in variables and
                'bottom_vosaline' not in variables):
            anom = False
        if anom:
            variable_name += " Anomaly"

        depth = 0
        depthm = 0
        if query.get('depth') and \
            len(query.get('depth')) > 0 and \
                query.get('depth') != 'all':
            depth = int(query.get('depth'))
            if depth >= dataset.variables['deptht'].shape[0]:
                depth = 0
            if 'deptht' in dataset.variables:
                depthm = dataset.variables['deptht'][int(depth)]
            else:
                depthm = 0
        data = []
        allvars = []
        for v in variables:
            var = dataset.variables[v]
            allvars.append(v)
            target_lat, target_lon, d = load_interpolated(
                m, 500, dataset, v,
                depth, time)
            data.append(d)
            if len(var.shape) == 3:
                depth_label = ""
            else:
                depth_var = dataset.variables['deptht']
                depth_label = " at " + \
                    str(int(np.round(depthm))) + " " + depth_var.units

        quiver_data = []
        if 'quiver' in query and len(query.get('quiver')) > 0:
            quiver_vars = query.get('quiver').split(',')
            for v in quiver_vars:
                if v is None or len(v) == 0 or v == 'none':
                    continue
                allvars.append(v)
                var = dataset.variables[v]
                quiver_unit = var.units
                quiver_name = var.long_name
                quiver_lat, quiver_lon, d = load_interpolated(
                    m, 50, dataset, v, depth, time)
                quiver_data.append(d)

            if quiver_vars[0] != 'none':
                quiver_name = re.sub(r"(?i)( x | y |zonal |meridional )", " ",
                                     quiver_name)
                quiver_name = re.sub(r" +", " ", quiver_name)

        if all(map(lambda v: len(dataset.variables[v].shape) == 3, allvars)):
            depth = 0

        contour_data = []
        contour = query.get('contour')
        if contour is not None and \
            contour != '' and \
                contour != 'none':
            target_lat, target_lon, d = load_interpolated(m, 500, dataset,
                                                          contour,
                                                          depth, time)
            if dataset[contour].units == "Kelvins":
                d = np.add(d, -273.15)

            contour_data.append(d)
            contour_name = dataset.variables[contour].long_name

        t = netcdftime.utime(dataset.variables["time_counter"].units)
        timestamp = t.num2date(dataset.variables["time_counter"][time])

    # Load bathymetry data
    bathymetry = overlays.bathymetry(m, target_lat, target_lon, blur=2)
    if len(quiver_data) > 0 and int(depth) != 0:
        quiver_bathymetry = overlays.bathymetry(m, quiver_lat, quiver_lon)

    if int(depth) != 0:
        for d in data:
            d[np.where(bathymetry < depthm)] = np.ma.masked
        for d in quiver_data:
            d[np.where(quiver_bathymetry < depthm)] = np.ma.masked
        for d in contour_data:
            d[np.where(bathymetry < depthm)] = np.ma.masked
    else:
        for d in data:
            mask = maskoceans(target_lon, target_lat, d).mask
            d[~mask] = np.ma.masked
        for d in quiver_data:
            mask = maskoceans(quiver_lon, quiver_lat, d).mask
            d[~mask] = np.ma.masked
        for d in contour_data:
            mask = maskoceans(target_lon, target_lat, d).mask
            d[~mask] = np.ma.masked

    # Anomomilies
    if anom:
        with Dataset(climate_url, 'r') as dataset:
            target_lat, target_lon, d = load_interpolated(
                m, 500, dataset, variables[0],
                depth, timestamp.month - 1)
        data[0] = data[0] - d

    # Colormap from arguments
    cmap = query.get('colormap')
    if cmap is not None:
        cmap = colormap.colormaps.get(cmap)
    if cmap is None:
        if anom:
            cmap = colormap.colormaps['anomaly']
        else:
            cmap = colormap.find_colormap(variable_name)

    # Figure size
    # TODO: kwargs
    size = kwargs.get('size').replace("x", " ").split()
    figuresize = (float(size[0]), float(size[1]))
    fig = plt.figure(figsize=figuresize, dpi=float(kwargs.get('dpi')))

    if variable_unit == "Kelvins":
        variable_unit = "Celsius"
        for idx, val in enumerate(data):
            data[idx] = np.add(val, -273.15)

    if vector:
        mag = np.sqrt(data[0] ** 2 + data[1] ** 2)
        if scale:
            vmin = scale[0]
            vmax = scale[1]
        else:
            vmin = 0
            vmax = np.amax(mag)
            if query.get('colormap') is None or \
               query.get('colormap') == 'default':
                cmap = colormap.colormaps.get('speed')

        c = m.imshow(mag, vmin=vmin, vmax=vmax, cmap=cmap)

    else:
        if scale:
            vmin = scale[0]
            vmax = scale[1]
        else:
            vmin = np.inf
            vmax = -np.inf

            for d in data:
                vmin = min(vmin, np.amin(d))
                vmax = max(vmax, np.amax(d))
                if re.search("free surface", variable_name) or \
                    re.search("velocity", variable_name) or \
                    re.search("wind", variable_name) or \
                        anom:
                    vmin = min(vmin, -vmax)
                    vmax = max(vmax, -vmin)
                    if variable_unit == "fraction":
                        vmin = 0
                        vmax = 1

        c = m.imshow(data[0], vmin=vmin, vmax=vmax, cmap=cmap)

    if len(quiver_data) == 2:
        qx = quiver_data[0]
        qy = quiver_data[1]
        quiver_mag = np.sqrt(qx ** 2 + qy ** 2)

        # TODO: this is probably busted.
        if query.get('variable') == query.get('quiver'):
            qx /= quiver_mag
            qy /= quiver_mag
            qscale = 150
        else:
            qscale = None

        q = m.quiver(quiver_lon, quiver_lat,
                     qx, qy,
                     latlon=True, width=0.0025,
                     headaxislength=4, headlength=4,
                     scale=qscale,
                     pivot='mid'
                     )

        if query.get('variable') != query.get('quiver'):
            unit_length = np.mean(quiver_mag) * 2
            unit_length = np.round(unit_length,
                                   -int(np.floor(np.log10(unit_length))))
            if unit_length >= 1:
                unit_length = int(unit_length)

            plt.quiverkey(q, .65, .01,
                          unit_length,
                          quiver_name.title() + " " +
                          str(unit_length) + " " + quiver_unit,
                          coordinates='figure',
                          labelpos='E')

    if bool(query.get('bathymetry')):
        # Plot bathymetry on top
        cs = m.contour(
            target_lon, target_lat, bathymetry, latlon=True,
            lineweight=0.5,
            norm=LogNorm(vmin=1, vmax=6000),
            cmap=colormap.colormaps['transparent_gray'],
            levels=[100, 200, 500, 1000, 2000, 3000, 4000, 5000, 6000])
        plt.clabel(cs, fontsize='xx-small', fmt='%1.0fm')

    if query.get('overlay') and query.get('overlay') != 'none':
        overlays.draw_overlay(m, query.get('overlay'),
                              labelcolor='k',
                              edgecolor='k',
                              # facecolor='rnd',
                              # alpha=0.2,
                              linewidth=0.5)

    if len(contour_data) > 0:
        cs = m.contour(
            target_lon, target_lat, contour_data[0], latlon=True,
            lineweight=1, cmap=colormap.find_colormap(contour_name))
        plt.clabel(cs, fontsize='xx-small')

    # NAFO divisions
    # overlays.nafo_divisions(m)
    # overlays.draw_overlay(m, 'NAFO_Divisions',
    #                       labelcolor='k',
    #                       edgecolor='k',
    # facecolor='rnd',
    # alpha=0.2,
    #                       linewidth=0.5)

    # Map Info
    m.drawmapboundary(fill_color=(0.3, 0.3, 0.3))
    m.drawcoastlines(linewidth=0.5)
    m.fillcontinents(color='grey', lake_color='dimgrey')
    m.drawparallels(
        np.arange(
            round(np.amin(target_lat), -1),
            round(np.amax(target_lat), -1),
            5
        ), labels=[1, 0, 0, 0], color=(0, 0, 0, 0.5))
    m.drawmeridians(
        np.arange(
            round(np.amin(target_lon), -1),
            round(np.amax(target_lon), -1),
            10
        ), labels=[0, 0, 0, 1], color=(0, 0, 0, 0.5), latmax=85)

    if 'monthly' in url:
        dformat = "%B %Y"
    else:
        dformat = "%d %B %Y"

    plt.title(variable_name.title() + depth_label +
              ", " + timestamp.strftime(dformat))
    divider = make_axes_locatable(plt.gca())
    cax = divider.append_axes("right", size="5%", pad=0.05)
    bar = plt.colorbar(c, cax=cax)
    bar.set_label(variable_name.title() + " (" + variable_unit + ")")
    fig.tight_layout(pad=3, w_pad=4)

    # Output the plot
    buf = cStringIO.StringIO()
    try:
        plt.savefig(buf, format='png')
        plt.close(fig)
        return buf.getvalue()
    finally:
        buf.close()