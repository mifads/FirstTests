#!/usr/bin/env python3
"""
  Reads TNO MACC/CAMS format emission file and stores as dictionary giving
  e.g.:
    Emis['NH3']['NOR']['C:A']['sum'] for sum of GNFR sector C (:A = area)
    Emis['snap2']['PMc']['NOR']] for small combustion (=special!)
  or Emis['NOX']['NOR']['A:P']['vals'][:,:] for 2-D mapping of that sector

  Updated Nov 2019 - Apr 2020 for new sector possibilities, and to use pandas
  previously maccInfo:  July 2017

  Warning 1. Too complex, and not yet re-working for older MACC style, which
  had irregular lon/lat coords. Easily fixed, but not done. Works for new
  CAMS though.

  Warning 2. Uses lots of memory and takes time!
"""
from collections import OrderedDict as odict
import copy
import gc
import os
import pandas as pd
import sys
import numpy as np

Usage="""
  Usage:
     camsInfo.py tno_emission_file
  e.g.
     cams2Info.py TNO_MACC_III_emissions_v1_1_2011.txt

"""

camsInfo = odict()

# Emissions files, e.g.:
# TNO emissions 2017-ish:
#Lon;Lat;ISO3;Year;SNAP;SourceType;CH4;CO;NH3;NMVOC;NOX;PM10;PM2_5;SO2
#-29.937500;36.406250;ATL;2011;8;A;0.000000;0.063392;0.000000;0.018761;0.634203;0.048957;0.046509;0.417624
# CAMS Nov 2019:
#Lon_rounded;Lat_rounded;ISO3;Year;GNFR_Sector;SourceType;CH4;CO;NH3;NMVOC;NOX;PM10;PM2_5;SO2
#-29.950000000;60.025000000;ATL;2016;G;A;0.000000000;5.658706000;0.000000000;0.810892000;107.728119000;8.422509000;8.422509000;65.927017000
#    idbg=316; jdbg=416 # DK

polls = 'CO NH3 NMVOC NOX PM10 PM2_5 PMc SO2'.split()  # TNO  style, skip CH4

def nicefloat(x):
  """ converts eg 0.09999999999787 to 0.1 """
  return float('%12.6f' % x)

def nicefloats(xlist):
  return [ nicefloat(x) for x in xlist ]

def src_name(sec_key, sec, typ):
  """ Returns compound name, e.g. A1:P.  If SNAP, use 2-digit sector name,
      e.g. 01:P """
  if sec_key == 'SNAP':
    return '%2.2d:%s' % (sec, typ)  #  could be int, e.g. 7, in SNsrc system
  else:
    return '%s:%s' % (sec, typ)  #  could be int, e.g. 7, in SNsrc system

def check_ranges(coords,txt):
  """ checks the lon or lat coordinates to find min and max spacing 
      since the values are sometimes irregular  """
  dmin= 999; dmax= -999
  for i in range(1,len(coords)):
    dcoord= coords[i]-coords[i-1]
    if dcoord < dmin: dmin=dcoord
    if dcoord > dmax: dmax=dcoord
  dcoord= coords[1]-coords[0] # Hopefully a good dx, dy guess
  print( txt, ' coords', nicefloats([ dcoord, coords[0], coords[-1], 
     coords[-1]-coords[0], (coords[-1]-coords[0])/dcoord, dmin, dmax ] ) )
  assert abs(dmax-dmin) < 1.0e-9,'IRREGULAR COORDS %s %f %f %12.3e' % (txt, dmin, dmax, dmax-dmin)
#  assert dmax>dmin,'AIRREGULATE COORDS %s %f %f' % (txt, dmin, dmax)
#  assert dmax<dmin,'BIRREGULATE COORDS %s %f %f %f' % (txt, dmin, dmax, dmax-dmin)


def readCams(ifile,wanted_poll=None,get_vals=False,dbgcc=None,dbg=None):

    print('Reading %s;\n *** can take a while!' % ifile )
    df = pd.read_csv(ifile,sep=';')
    if dbg: df.info(memory_usage='deep')
    
    used_polls = polls
    if wanted_poll == 'PMc' or wanted_poll == 'PM':
      used_polls = 'PM2_5 PM10 PMc'.split()
    elif wanted_poll is not None:
      used_polls = [ wanted_poll, ]
    if wanted_poll == 'PM': wanted_poll = None # no longer needed

    if 'PMc' in used_polls and 'PMc' not in df.keys():
       print('PM is wanted: special handling for PMc' )
       df['PMc'] =  df['PM10'] - df['PM2_5']
    elif wanted_poll is not None: 
       assert wanted_poll in df.keys(), '!! POLL not found: ' + wanted_poll

    print('KEYS', wanted_poll, df.keys() )
    #df.info(memory_usage='deep')
    #df.to_sparse().info(memory_usage='deep')

    # 1-d fields:
    lonList    = df.iloc[:,0].values  # Name can change between MACC/CAMS
    latList    = df.iloc[:,1].values
    iso3List   = df.ISO3.values
    sec_key    = df.keys()[4]   # eg GNFR_Sector or SNAP
    typ_key    = df.keys()[5]   #  SourceType A or P
    secList    = df[sec_key].values
    typList    = df.SourceType.values
    iso3s = np.unique(iso3List)
    EurTot = 'EurTot'  # sum of all countries
    iso3s = np.append(iso3s,EurTot)
    if dbgcc is not None: print('DBGISO3s: ',iso3s)
    if dbg   is not None: print('DBGISO3s: ',iso3s)
    
    sectors = sorted( df[sec_key].unique() )
    types   = sorted( df[typ_key].unique() )
    countryTot = 'Sum:secs'  # Sum for each country
    srcs = []
    for sec, typ in zip( secList, typList ):
       srcs.append( src_name( sec_key, sec, typ) )

    srcs = np.unique(srcs)  #  np unique also sorts
    srcs = np.append(srcs,countryTot) # at end
    #dbgcc_srcs = dict.fromkeys(srcs,0.0)
    print('Zipped list from sec_key, typ_key', srcs, len(srcs) )

   # Find lon/lat ranges and dimensions
   # look for max and min, BUT tno spacings are not always regular
   # Hopefully the distance 0 to 1 is
    lons = np.unique( lonList ) # Unique list, sorted W to E
    lats = np.unique( latList ) # Unique list, sorted S to N 

    dx  = nicefloat( lons[1]  - lons[0] )
    dy  = nicefloat( lats[1]  - lats[0] )

    xmin= nicefloat( lons[0]  - 0.5*dx  )  # left edge, here -30
    xmax= nicefloat( lons[-1] + 0.5*dx  )  # right edge, here 60.125
    ymin= nicefloat( lats[0]  - 0.5*dy  )  # bottom edge, here 30.0  
    ymax= nicefloat( lats[-1] + 0.5*dy  )  # top edge, here 72.0
    nlons= int( (xmax-xmin)/dx )  +  1  # +1 needed to cope with uneven longitude range
    nlats= int( (ymax-ymin)/dy )  +  1
    newxmax =  xmin + nlons*dx
    newymax =  ymin + nlats*dy
    # safety (in case dx ain't very big!):
    assert  newxmax > xmax, 'x Coordinate problem: %f < %f ' % (newxmax, xmax)
    assert  newymax > ymax, 'y Coordinate problem: %f < %f ' % (newymax, ymax)
    print( 'minmax coords', ymin, ymax, newymax, xmin, xmax, newxmax  )
    
    check_ranges(lons,'Lon')    #  checking linearity of longitude:
    check_ranges(lats,'Lat')
    

    srcEmis =  dict()
    srcEmis['polls']=used_polls.copy()
    srcEmis['iso3s']= iso3s
    srcEmis['srcs'] = srcs
    srcEmis['snap2']= dict() # special
    srcEmis['lons']=lons.copy()
    srcEmis['lats']=lats.copy()
    srcEmis['dx']=dx
    srcEmis['dy']=dy

    for poll in used_polls: #  'NOX',: 

       vals = df[poll].values
       print('Process poll: max vals ', poll, np.max(vals) )

       # Initialise dict()
       srcEmis[poll]  = dict()
       if poll.startswith('PM'): srcEmis['snap2'][poll] = dict()
       for iso3 in iso3s:
         srcEmis[poll][iso3] = dict()
         if poll.startswith('PM'): 
           srcEmis['snap2'][poll][iso3] = 0.0 # special
         for src in srcs:
           srcEmis[poll][iso3][src] = dict()
           srcEmis[poll][iso3][src]['sum']  =  0.0
           #if get_vals is not None:
           if get_vals:
             srcEmis[poll][iso3][src]['vals'] =  np.zeros([nlats,nlons])
     #      print('Init src ', src)
      
       for n in range(len(df)): # with open(ifile) as f:
    
          iso3       = iso3List[n]
          sec        = secList[n]
          typ        = typList[n]
          lon        = lonList[n]
          lat        = latList[n]
   
          ix  = int( (lon-xmin)/dx )
          iy  = int( (lat-ymin)/dy )
          assert ix < nlons and  iy < nlats, \
            'OOPSXY %6.3f %6.3f %s %d %d %d %d'% ( 
                    lon, lat, iso3, ix, iy, nlons, nlats  )
    
          src  = src_name(sec_key, sec, typ)  # e.g. H:P or A2:A or 07:A

          x =  vals[n]

          #if iso3==dbgcc:
          #  dbgcc_srcs[src] += x
          #  print('DBGCC ', n, sec, typ, src, x, dbgcc_srcs['K:A'])

          srcEmis[poll][iso3][src]['sum']    += x
          srcEmis[poll][iso3][countryTot]['sum']  += x
          srcEmis[poll][EurTot][src]['sum']  += x
          srcEmis[poll][EurTot][countryTot]['sum']  += x
          if src=='C:A' and poll.startswith('PM'):
                srcEmis['snap2'][poll][iso3] += x
          #print('GET VALS?', get_vals)
          #MAR2020 if get_vals is not None:
          if get_vals:
             srcEmis[poll][iso3][src]['vals'][iy,ix] += x
     
#          if ix == idbg and iy==jdbg: 
#            print('DBG ', poll, lon, lat, src, x, srcEmis[src][iso3][iy,ix] )

    # Try to release memory
    del df
    gc.collect()
    df = pd.DataFrame()

    if dbgcc is not None:
      if wanted_poll is 'PMc': used_polls.append('PMc')
      print('Summary, kt, %s' % ifile) 
      print('used (kt)', used_polls ) 
      print('%8s' % 'src', end='')
      for poll in used_polls: print('%12s' % poll, end='')
      print()
      for src in srcs:
        print('%8s' % src, end='')
        for poll in used_polls:
          print('%12.4e' % ( 0.001*srcEmis[poll][dbgcc][src]['sum']),
                  end='') # kt
        print()

    return srcEmis
   
    
if __name__ == '__main__':

  Usage="""
    camsInfo.py  -h 
     or
    camsInfo.py  TNO_file   (ascii, semicolon separated)
  """
  print('MAIN ', sys.argv)
  if 'ipython' in sys.argv[0]:
    ifile = 'TestCamsInfo.txt'
    #ifile='/home/davids/Work/D_Emis/TNO_Emis/TNO_Inputs/CAMS-REG-AP_v2.2.1_2015_REF2.csv'
  else:
    if len(sys.argv) < 2:   sys.exit('\nError! Usage:\n' + Usage)
    if sys.argv[1] == '-h': sys.exit('\nUsage: \n' + Usage)
    ifile=sys.argv[1]

  assert  os.path.exists(ifile), '\nError!\n File does not exist: '+ifile

  print('IFILE', ifile)

  # ==========================================================

  dbgcc='KWT'
  dbgPoll='CO'
  dbgPoll='NOX'
  dbgPoll='NMVOC'
  dbgPoll='PM'
  dbgcc='EurTot'
  m=readCams(ifile,wanted_poll=dbgPoll,get_vals=False,dbgcc=dbgcc)  #PMc is special

  if dbgPoll == 'PM':
    print('EXAMPLE gnfr:', m['PMc'][dbgcc]['C:A']['sum'])
    print('EXAMPLE snap2:', m['snap2']['PM2_5'][dbgcc] )
  else:
    print('EXAMPLE C gnfr:', m[dbgPoll][dbgcc]['C:A']['sum'])
  # ==========================================================

  gc.collect() # recover some memory?

  # here we get spatial values. Seems to work, but can be memory problems
  #v=readCams(ifile,wanted_poll='PM',get_vals=True,dbgcc='Total')  #PMc is special
  #v=readCams(ifile,get_vals=True,dbgcc='Total')  #PMc is special


