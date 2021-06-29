import json
import time
import requests
import pandas as pd
import credentials as cd
import space_names as sn 

from copy import deepcopy
from datetime import datetime, timedelta
from influxdb import InfluxDBClient, DataFrameClient
from influxdb.exceptions import InfluxDBServerError

class UserProgress():
    def __init__(self, min_votes=80, min_time_between_votes=15, loc_threshold_time_tol=10):
        """
        Arguments for minimum time between votes and the time tolerance
        for the location threshold are in minutes
        """
        # experiment specific
        self.spaces_dict = sn.space_names
        self.min_votes = min_votes
        self.min_time_between_votes = min_time_between_votes # min
        self.loc_threshold_time_tol = loc_threshold_time_tol # min 

        # connect to Influx
        self.influx_cl = InfluxDBClient(host=cd.host, 
                                        port=cd.port, 
                                        username=cd.usr,
                                        password=cd.passwd,
                                        database=cd.database,
                                        ssl=True,
                                        verify_ssl=True)
        
    def influx_to_df(self, query):
        try:
            result = self.influx_cl.query(query)
            df = pd.DataFrame(result[result.keys()[0]])
            df.index = pd.to_datetime(df.time)
            df.index = df.index.tz_convert(cd.time_zone)
            return df.drop(columns=['time'])
        except IndexError:
            return pd.DataFrame()

    def last_vote(self, participant_id): 
        query_vote = f'SELECT "thermal" FROM {cd.database}.autogen.{cd.measurement} WHERE userid=\'{participant_id}\' ORDER BY time Desc LIMIT 1'
        df_last_vote = self.influx_to_df(query_vote)
        # at least one datapoint should be available
        if df_last_vote.empty:
            return None, None, None
        msg_timestamp = df_last_vote.index[0]

        last_msg_time = (pd.Timestamp.now(cd.time_zone) - msg_timestamp).total_seconds()/60 # min
        
        if last_msg_time >= 2*24*60: # check if 2 days have passed
            last_msg_time = last_msg_time/(24*60) # convert from min to days
            time_unit = 'days'
        elif last_msg_time >= 60: # check if more than 1 hour have passed 
            last_msg_time /= 60 # convert from min to hour
            time_unit = 'hours'
        else:
            time_unit = 'minutes'

        return last_msg_time, time_unit, msg_timestamp

    def daily_report(self, participant_id):
        """
        Calculates a breakdown of valid, unvalid, and remaining data points
        for a specific user
        """

        all_thermal = []
        valid_points = []
        invalid_points = []
        points_within_sde = []
        prev_time = None 
        delta_time = None 
        
        # query cozie responses and locations for the same user, then merge them
        query_cozie = f'SELECT "thermal" FROM {cd.database}.autogen.{cd.measurement} WHERE time < now() AND userid=\'{participant_id}\''
        df_user = self.influx_to_df(query_cozie)
        query_loc = f'SELECT * FROM SteerPath.autogen.Steerpath WHERE time < now() AND Userid=\'{participant_id}\' GROUP BY * ORDER BY time'
        df_loc = self.influx_to_df(query_loc)
        # since the timestamp is the index, there cannot be more than one row with the same timestamp
        localised_user_df = pd.merge_asof(df_user, df_loc, left_index=True, right_index=True, tolerance=pd.Timedelta(minutes=self.loc_threshold_time_tol), direction='nearest')
        
        ### DEBUG
        localised_user_df.to_csv(f'data/{participant_id}_merged.csv')
        print(localised_user_df)
        ###

        # every vote so far for this user
        for time, data in localised_user_df.iterrows():
            try:
                # verify if the cozie datapoint has steerpath readings 
                if pd.isnull(data['Longitude']) or pd.isnull(data['Latitude']):
                    # cozie vote was not given within range of a bluetooth beacon
                    continue # ignore this datapoint

                time_tz = time.astimezone(cd.time_zone)
                # keep track of previous vote time
                if prev_time == None: # only for the very first row
                    prev_time = deepcopy(time_tz)
                    delta_time = self.min_time_between_votes
                else:
                    # update time between votes 
                    delta_time = abs((time_tz - prev_time).total_seconds()/60)
                    if delta_time >= self.min_time_between_votes:
                        prev_time = deepcopy(time_tz)
                
                # two votes are extremly close in time and somehow both got registered to the database
                if delta_time == 0:
                    print(f'Duplicated cozie vote for {participant_id} at {time}')
                    continue # ignore this datapoint 

                # missing space_id is due to incomplete geofencing
                elif not pd.isnull(data['Space_id']):
                    spaces = data['Space_id']
                    longitudes = data['Longitude']
                    latitudes = data['Latitude'] 
                    loc_time = data.index
                else:
                    spaces = -1
                    longitudes = data['Longitude']
                    latitudes = data['Latitude'] 
                    loc_time = data.index
                
                # keep track of the votes that are valid or invalid 
                if delta_time >= self.min_time_between_votes:
                    points_within_sde.append({"space_name":self.spaces_dict[spaces],
                                             "longitude": longitudes,
                                             "latitude": latitudes, 
                                             "thermal":data["thermal"], 
                                             "time": str(time_tz),
                                             "type": "valid"
                    })
                    valid_points.append(delta_time)
                else:
                    points_within_sde.append({"space_name":self.spaces_dict[spaces],
                                              "longitude": longitudes,
                                              "latitude": latitudes, 
                                              "thermal":data["thermal"], 
                                              "time": str(time_tz),
                                              "type": "invalid"
                    })
                    invalid_points.append(delta_time)

            except Exception as e:
                error_msg = f'Daily report error for participant {participant_id}:\n' 
                error_msg += f'Space with space_id {e} not found in spaces file'
                return error_msg, len(valid_points)

            all_thermal.append(data['thermal'])
            # end for loop

        ### DEBUG
        #print(valid_points)
        #print(invalid_points)
        ###

        # format daily report message
        last_input = data
        msg = f'Hi {participant_id}, as of {pd.Timestamp.now(cd.time_zone).strftime("%b-%d %H:%M")}:\n'
        if len(valid_points) >= self.min_votes:
            msg += 'Congratulations! You completed at least 80 data points inside SDE buildings\n'
            # TODO: breakdown of current points
           
        if len(points_within_sde) > 0:
            msg += f'Total data points: {len(all_thermal)}\n'
            msg += f'Valid data points (within SDE): {len(valid_points)} out of {self.min_votes}\n'
            msg += f'Data points left: {80-len(valid_points) if len(valid_points) <= 80 else 0}\n'
        else:
            msg += 'You haven\'t recorded any valid data points yet\n'
            msg += 'Don\'t forget to turn on the YAK application and bluetooth before leaving feedback on the Fitbit smartwatch \n'
            
        return msg, len(valid_points)

