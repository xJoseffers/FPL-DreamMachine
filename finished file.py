import requests
import json 
import pandas as pd
from datetime import datetime, timedelta


def update_team(email, password, id):
    
    session = requests.session()

    players_df, fixtures_df, gameweek=get_data()

    data = {'login' : email, 'password' : password, 'app' : 'plfpl-web', 'redirect_uri' : 'https://fantasy.premierleague.com/'}
    login_url = "https://users.premierleague.com/accounts/login/"
    
    session.post(url=login_url, data=data)
    url = "https://fantasy.premierleague.com/api/my-team/" + str(id)
    team = session.get(url)
    team = json.loads(team.content)

    bank = team['transfers']['bank']

    players = [x['element'] for x in team['picks']]

    my_team = players_df.loc[players_df.id.isin(players)]
    potential_players = players_df.loc[~players_df.id.isin(players)]

    player_out = calc_out_weight(my_team)
    rows_to_drop=player_out.index.values.astype(int)[0]
    my_team=my_team.drop(rows_to_drop)

    position = player_out.element_type.iat[0]
    out_cost = player_out.now_cost.iat[0]
    budget = bank + out_cost
    dups_team = my_team.pivot_table(index=['team'], aggfunc='size')
    invalid_teams = dups_team.loc[dups_team==3].index.tolist()

    potential_players=potential_players.loc[~potential_players.team.isin(invalid_teams)]
    potential_players=potential_players.loc[potential_players.element_type==position]
    potential_players = potential_players.loc[potential_players.now_cost<=budget]

    player_in = calc_in_weights(potential_players)
    my_team = my_team.append(player_in)
    my_team = calc_starting_weight(my_team)

    goalies = my_team.loc[my_team.element_type==1]

    defenders = my_team.loc[my_team.element_type==2]
    outfied_players = my_team.loc[my_team.element_type>2]

    captain = outfied_players.id.iat[0]
    vice_captain = outfied_players.id.iat[1]

    starters = goalies.head(1).append(defenders.head(3)).append(outfied_players.head(7))
    subs = goalies.tail(1).append(defenders.tail(2)).append(outfied_players.tail(1))

    headers = {'content-type': 'application/json', 'origin': 'https://fantasy.premierleague.com', 'referer': 'https://fantasy.premierleague.com/transfers'}
    transfers = [{"element_in" : int(player_in.id.iat[0]), "element_out" : int(player_out.id.iat[0]),"purchase_price": int(player_in.now_cost.iat[0]), "selling_price" : int(player_out.now_cost.iat[0])}]
    transfer_payload = { "transfers" : transfers,"chip" : None,"entry" : id,"event" : int(gameweek)}
    url = 'https://fantasy.premierleague.com/api/transfers/'
    print("Transferring Out: " + player_out.web_name.iat[0] + ", Transferring In: " + player_in.web_name.iat[0])
    print("Starters: " + str(starters.web_name.tolist()))
    print("Subs: " + str(subs.web_name.tolist()))
    session.post(url=url, data=json.dumps(transfer_payload), headers=headers)
    
    picks =[]
    count = 1
    for i in range(1,5):
        players = starters.loc[starters.element_type==i]
        ids = players.id.tolist()
        for ide in ids:
            if ide == captain:
                player = {"element" : ide, "is_captain" : True, "is_vice_captain" : False, "position" : count}
            elif ide == vice_captain:
                player = {"element" : ide, "is_captain" : False, "is_vice_captain" : True, "position" : count}
            else:
                player = {"element" : ide, "is_captain" : False, "is_vice_captain" : False, "position" : count}
            picks.append(player.copy())
            count+=1
    ids = subs.id.tolist()
    for ide in ids:
        player = {"element" : ide, "is_captain" : False, "is_vice_captain" : False, "position" : count}
        picks.append(player.copy())
        count+=1
    team_sheet = {"picks" : picks,"chip" : None}
    headers = {'content-type': 'application/json', 'origin': 'https://fantasy.premierleague.com', 'referer': 'https://fantasy.premierleague.com/my-team'}
    url = 'https://fantasy.premierleague.com/api/my-team/'+str(id) + '/'
    session.post(url=url, json=team_sheet,headers=headers)

def get_data():

    
    players =  get('https://fantasy.premierleague.com/api/bootstrap-static/')
    players_df = pd.DataFrame(players['elements'])
    teams_df = pd.DataFrame(players['teams'])
    fixtures_df = pd.DataFrame(players['events'])
    today = datetime.now().timestamp()
    fixtures_df = fixtures_df.loc[fixtures_df.deadline_time_epoch>today]
    if check_update(fixtures_df) == False:
         print("Deadline Too Far Away")
         exit(0)
    gameweek =  fixtures_df.iloc[0].id
    players_df.chance_of_playing_next_round = players_df.chance_of_playing_next_round.fillna(100.0)
    players_df.chance_of_playing_this_round = players_df.chance_of_playing_this_round.fillna(100.0)
    fixtures = get('https://fantasy.premierleague.com/api/fixtures/?event='+str(gameweek))
    fixtures_df = pd.DataFrame(fixtures)

    
    teams=dict(zip(teams_df.id, teams_df.name))
    players_df['team_name'] = players_df['team'].map(teams)
    fixtures_df['team_a_name'] = fixtures_df['team_a'].map(teams)
    fixtures_df['team_h_name'] = fixtures_df['team_h'].map(teams)

    home_strength=dict(zip(teams_df.id, teams_df.strength_overall_home))
    away_strength=dict(zip(teams_df.id, teams_df.strength_overall_away))

    fixtures_df['team_a_strength'] = fixtures_df['team_a'].map(away_strength)
    fixtures_df['team_h_strength'] = fixtures_df['team_h'].map(home_strength)

    fixtures_df=fixtures_df.drop(columns=['id'])
    a_players = pd.merge(players_df, fixtures_df, how="inner", left_on=["team"], right_on=["team_a"])
    h_players = pd.merge(players_df, fixtures_df, how="inner", left_on=["team"], right_on=["team_h"])

    a_players['diff'] = a_players['team_a_strength'] - a_players['team_h_strength']
    h_players['diff'] = h_players['team_h_strength'] - h_players['team_a_strength']

    players_df = a_players.append(h_players)
    return players_df, fixtures_df, gameweek
def get(url):
    response = requests.get(url)
    return json.loads(response.content)

def check_update(df):
    
    today = datetime.now()
    tomorrow=(today + timedelta(days=1)).timestamp()
    today = datetime.now().timestamp()
    df = df.loc[df.deadline_time_epoch>today]
    
    deadline = df.iloc[0].deadline_time_epoch
    if deadline<tomorrow:
        return True
    else:
        return False

def calc_in_weights(players):
    players['weight'] = 1
    players['weight'] += players['diff']/3
    players['weight'] += players['form'].astype("float")*10
    players['weight'] -= (100 - players['chance_of_playing_this_round'].astype("float"))*0.2
    players.loc[players['weight'] <0, 'weight'] =0

    return players.sample(1, weights=players.weight)


def calc_out_weight(players):
    players['weight'] = 100
    players['weight']-= players['diff']/3
    players['weight']-= players['form'].astype("float")*10
    players['weight']+= (100 - players['chance_of_playing_this_round'].astype("float"))*0.2
    players.loc[players['element_type'] ==1, 'weight'] -=10
    players.loc[players['weight'] <0, 'weight'] =0

    return players.sample(1, weights=players.weight)

def calc_starting_weight(players):
    players['weight'] = 1
    players['weight'] += players['diff']/2
    players['weight'] += players['form'].astype("float")*5
    players['weight'] -= (100 - players['chance_of_playing_this_round'].astype("float"))*0.2
    players.loc[players['weight'] <0, 'weight'] =0
    return players.sort_values('weight', ascending=False)


def lambda_handler(event, context):
    email = "your_email"
    password = "your_password"
    user_id = "your_id"
    update_team(email, password,user_id)