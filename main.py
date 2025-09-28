import discord
from discord import app_commands
import json
import os
import requests
import asyncio
from typing import Dict, List, Any

# --- CONFIGURATION (Reads from Replit Secrets) ---
try:
    # Use os.getenv() to securely load variables from Replit Secrets
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    CHALLONGE_API_KEY = os.getenv("CHALLONGE_API_KEY")
    CHALLONGE_USERNAME = os.getenv("CHALLONGE_USERNAME")
    
    # REFEREE_ROLE_ID must be cast to an integer
    REFEREE_ROLE_ID = int(os.getenv("REFEREE_ROLE_ID"))
    
    if not all([DISCORD_BOT_TOKEN, CHALLONGE_API_KEY, CHALLONGE_USERNAME, REFEREE_ROLE_ID]):
        raise ValueError("One or more required secrets are missing or empty.")
except (TypeError, ValueError) as e:
    print(f"\n❌ CONFIGURATION ERROR: Failed to load environment variables. Have you set DISCORD_BOT_TOKEN, CHALLONGE_API_KEY, CHALLONGE_USERNAME, and REFEREE_ROLE_ID in Replit Secrets? Error: {e}\n")
    exit(1)

TEAM_SIZE_LIMIT = 5
DATA_FILE = 'tournament_data.json'

# --- DATA STRUCTURES (Loaded from file) ---
# Global data dictionary for persistence
data = {
    'teams': {},
    'tournament_id': None,
    'match_threads': {},
    'challonge_matches': {}
}

# --- HELPER FUNCTIONS ---

def load_data():
    """Loads tournament data from JSON file."""
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                # Ensure player IDs are stored/loaded as integers for lookup efficiency
                loaded_data = json.load(f)
                
                # Convert player IDs back to integers if stored as strings (JSON default)
                if 'teams' in loaded_data:
                    data['teams'] = {
                        team: [int(pid) for pid in player_ids] 
                        for team, player_ids in loaded_data['teams'].items()
                    }
                
                # Update other keys
                for key in ['tournament_id', 'match_threads', 'challonge_matches']:
                     if key in loaded_data:
                         data[key] = loaded_data[key]

                print("Data loaded successfully.")
            except json.JSONDecodeError:
                print("Error loading JSON data. Starting with empty data.")
    else:
        print("Data file not found. Starting with empty data.")

def save_data():
    """Saves tournament data to JSON file."""
    # Convert integer IDs in the 'teams' list to strings for safe JSON serialization
    serializable_data = data.copy()
    serializable_data['teams'] = {
        team: [str(pid) for pid in player_ids] 
        for team, player_ids in data['teams'].items()
    }
    
    with open(DATA_FILE, 'w') as f:
        json.dump(serializable_data, f, indent=4)
    print("Data saved successfully.")

# --- CHALLONGE API FUNCTIONS ---

BASE_URL = f"https://api.challonge.com/v1/tournaments"

def challonge_api_call(method, endpoint, json_data=None):
    """Generic function to interact with the Challonge API."""
    # Note the API URL now incorporates the username/subdomain for endpoint construction
    url = f"{BASE_URL}/{CHALLONGE_USERNAME}{endpoint}.json"
    print(f"DEBUG: Attempting {method} to URL: {url}")
    params = {'api_key': CHALLONGE_API_KEY}
    headers = {'Content-Type': 'application/json'}
    
    try:
        if method == 'POST':
            response = requests.post(url, params=params, json=json_data, headers=headers)
        elif method == 'PUT':
            response = requests.put(url, params=params, json=json_data)
        elif method == 'GET':
            response = requests.get(url, params=params)
        elif method == 'DELETE':
            response = requests.delete(url, params=params)
        else:
            return None, "Invalid HTTP method"
        
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        return response.json(), None
    except requests.exceptions.HTTPError as e:
        # Include detailed error info from Challonge if available
        try:
            error_details = e.response.json()
            error_message = f"HTTP Error {e.response.status_code}: {error_details.get('errors', ['Unknown Challonge Error'])[0]}"
        except:
             error_message = f"HTTP Error {e.response.status_code}: {e.response.text}"
        return None, error_message
    except requests.exceptions.RequestException as e:
        return None, f"Request Error: {e}"

# --- DISCORD BOT SETUP ---

class TournamentBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        load_data()
        await self.tree.sync()
        print('Synced application commands.')

intents = discord.Intents.default()
intents.members = True # Required for member lookup and pings
client = TournamentBot(intents=intents)

# --- SLASH COMMANDS ---

# /register_team <team_name> <player_1> ... <player_5>
@client.tree.command(name="register_team", description=f"Register a new team (max {TEAM_SIZE_LIMIT} players).")
@app_commands.describe(
    team_name="The name of the team.",
    p1="Player 1 (required)",
    p2="Player 2", p3="Player 3", p4="Player 4", p5="Player 5"
)
async def register_team(interaction: discord.Interaction, team_name: str, p1: discord.Member, p2: discord.Member = None, p3: discord.Member = None, p4: discord.Member = None, p5: discord.Member = None):
    """Registers a new team and stores member IDs."""
    
    if data['tournament_id']:
        await interaction.response.send_message("❌ A tournament is already active. Please delete it first with `/delete_tournament`.", ephemeral=True)
        return
        
    team_name = team_name.strip()
    if team_name in data['teams']:
        await interaction.response.send_message(f"❌ Team **{team_name}** is already registered.", ephemeral=True)
        return

    players = [p for p in [p1, p2, p3, p4, p5] if p is not None]
    player_ids = []
    
    # Check for duplicate players and collect IDs
    seen_ids = set()
    for player in players:
        if player.id in seen_ids:
             await interaction.response.send_message(f"❌ Player **{player.display_name}** is listed more than once.", ephemeral=True)
             return
        player_ids.append(player.id)
        seen_ids.add(player.id)

    # Check if any player is already on another team
    for existing_team, existing_ids in data['teams'].items():
        for player_id in player_ids:
            if player_id in existing_ids:
                member = interaction.guild.get_member(player_id)
                await interaction.response.send_message(f"❌ Player **{member.display_name if member else player_id}** is already registered in team **{existing_team}**.", ephemeral=True)
                return

    data['teams'][team_name] = player_ids
    save_data()
    
    mentions = " ".join([p.mention for p in players])
    
    await interaction.response.send_message(
        f"✅ Team **{team_name}** registered successfully with {len(players)} players: {mentions}",
        allowed_mentions=discord.AllowedMentions(users=True)

    )


# /remove_team <team_name>
@client.tree.command(name="remove_team", description="Remove a team from registration.")
@app_commands.describe(team_name="The name of the team to remove.")
async def remove_team(interaction: discord.Interaction, team_name: str):
    """Removes a registered team."""
    
    if data['tournament_id']:
        await interaction.response.send_message("❌ A tournament is active. Please delete it first with `/delete_tournament`.", ephemeral=True)
        return
        
    team_name = team_name.strip()
    if team_name in data['teams']:
        del data['teams'][team_name]
        save_data()
        await interaction.response.send_message(f"✅ Team **{team_name}** has been removed from registrations.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Team **{team_name}** was not found in registrations.", ephemeral=True)


# /remove_player <player>
@client.tree.command(name="remove_player", description="Remove a player from their registered team.")
@app_commands.describe(player="The player to remove.")
async def remove_player(interaction: discord.Interaction, player: discord.Member):
    """Removes a player from whichever team they belong to."""
    
    if data['tournament_id']:
        await interaction.response.send_message("❌ A tournament is active. Please delete it first with `/delete_tournament`.", ephemeral=True)
        return
        
    player_id = player.id
    
    for team_name, player_ids in list(data['teams'].items()):
        if player_id in player_ids:
            player_ids.remove(player_id)
            
            # Optionally remove the team if it's now empty
            if not player_ids:
                del data['teams'][team_name]
                
            save_data()
            await interaction.response.send_message(f"✅ Player **{player.display_name}** removed from team **{team_name}**.", ephemeral=True)
            return

    await interaction.response.send_message(f"❌ Player **{player.display_name}** was not found on any registered team.", ephemeral=True)

# /create_brackets <tournament_name>
@client.tree.command(name="create_brackets", description="Creates brackets on Challonge using registered teams.")
@app_commands.describe(tournament_name="The name of the tournament (e.g., 'Season 1')")
async def create_brackets(interaction: discord.Interaction, tournament_name: str):
    """Creates a Challonge tournament and initializes the bracket."""
    await interaction.response.defer(ephemeral=True)
  
    if interaction.guild is None:
        await interaction.followup.send("❌ This command must be run within a Discord server channel, not a Direct Message.", ephemeral=True)
        return

    if data['tournament_id']:
        await interaction.followup.send("❌ A tournament is already active. Use `/delete_tournament` first.")
        return

    teams = list(data['teams'].keys())
    if len(teams) < 2:
        await interaction.followup.send("❌ Need at least 2 teams to create a tournament.")
        return
        
    # 1. Create Tournament on Challonge
    # Use a clean URL/Slug (required by Challonge)
    tournament_slug = tournament_name.lower().replace(" ", "_").replace("'", "")[:20]
    
    tournament_data = {
        "tournament": {
            "name": tournament_name,
            "url": tournament_slug, # Provide a custom URL
            "tournament_type": "single elimination",
            "open_signup": False,
            "hold_third_place_match": True,
            "subtitle": f"Discord Bot Tournament - {interaction.guild.name}",
            "private": False
        }
    }
    
    result, error = challonge_api_call('POST', '', json_data=tournament_data)
    if error:
        await interaction.followup.send(f"❌ Error creating Challonge tournament: {str(error)[:1900]}")

        return

    # Use the actual slug returned by Challonge (usually matches the provided URL)
    actual_tournament_slug = result['tournament']['url']
    data['tournament_id'] = actual_tournament_slug 

    # 2. Add Participants (Teams)
    for team_name in teams:
        participant_data = {"participant": {"name": team_name}}
        # API endpoint for adding participants uses the tournament slug
        result, error = challonge_api_call('POST', f"/{actual_tournament_slug}/participants", json_data=participant_data)
        if error:
            # Clean up the tournament if participant creation fails
            challonge_api_call('DELETE', f"/{actual_tournament_slug}")
            data['tournament_id'] = None
            save_data()
            await interaction.followup.send(f"❌ Error adding team **{team_name}** to Challonge: {error}. Tournament creation aborted.")
            return

    # 3. Start Tournament to Generate Brackets
    result, error = challonge_api_call('POST', f"/{actual_tournament_slug}/start")
    if error:
        await interaction.followup.send(f"❌ Tournament created but **failed to start** and generate brackets: {error}. You may need to start it manually on Challonge.")
        save_data()
        return

    save_data()
    
    challonge_url = f"https://challonge.com/{actual_tournament_slug}"
    await interaction.followup.send(
        f"✅ Tournament **{tournament_name}** created and brackets generated! 🎉\n"
        f"**Challonge Link:** {challonge_url}\n"
        f"Run `/create_threads` to start the first round matches."
    )


# /create_threads
@client.tree.command(name="create_threads", description="Creates threads for all available matches.")
async def create_threads(interaction: discord.Interaction):
    """Fetches open matches from Challonge and creates Discord threads for them."""
    await interaction.response.defer()

    tournament_id = data.get('tournament_id')
    if not tournament_id:
        await interaction.followup.send("❌ No active tournament. Use `/create_brackets` first.")
        return

    # 1. Get participants (required to map IDs to names)
    participants_result, error = challonge_api_call('GET', f"/{tournament_id}/participants")
    if error:
         await interaction.followup.send(f"❌ Error fetching participants: {error}")
         return
    participant_map = {str(p['participant']['id']): p['participant']['name'] for p in participants_result}

    # 2. Get current matches from Challonge
    matches_result, error = challonge_api_call('GET', f"/{tournament_id}/matches")
    if error:
        await interaction.followup.send(f"❌ Error fetching matches from Challonge: {error}")
        return

    new_threads_created = 0
    message_content = "### Match Threads Created\n"
    
    referee_role = interaction.guild.get_role(REFEREE_ROLE_ID)
    if not referee_role:
        message_content += f"⚠️ Warning: Referee role with ID `{REFEREE_ROLE_ID}` not found in this server.\n"

    for match_wrapper in matches_result:
        match = match_wrapper['match']
        match_id = str(match['id'])
        
        # Condition for thread creation: 'open' state AND no existing thread
        if match['state'] == 'open' and match_id not in data['match_threads']:
            
            p1_id = str(match['player1_id'])
            p2_id = str(match['player2_id'])
            
            # Check if both participants are known (prevent threads for BYEs or future matches)
            if p1_id == 'None' or p2_id == 'None':
                 continue # Skip matches that don't have two confirmed opponents yet

            team1_name = participant_map.get(p1_id, f"ID:{p1_id}")
            team2_name = participant_map.get(p2_id, f"ID:{p2_id}")

            # Lookup Discord members
            team1_members = [interaction.guild.get_member(uid) for uid in data['teams'].get(team1_name, [])]
            team2_members = [interaction.guild.get_member(uid) for uid in data['teams'].get(team2_name, [])]
            
            p1_mentions = " ".join([m.mention for m in team1_members if m])
            p2_mentions = " ".join([m.mention for m in team2_members if m])
            ref_mention = referee_role.mention if referee_role else f"Referee (ID:{REFEREE_ROLE_ID})"
            
            thread_name = f"Round {match['round']}: {team1_name} vs {team2_name}"
            
            try:
                # Create the thread in the channel where the command was run
                thread = await interaction.channel.create_thread(
                    name=thread_name,
                    auto_archive_duration=60 # Archive after 1 hour of inactivity
                )
                
                # Send the initial ping message
                await thread.send(
                    f"⚔️ **Match Alert!** ⚔️\n\n"
                    f"**Team 1:** {team1_name} - {p1_mentions}\n"
                    f"**Team 2:** {team2_name} - {p2_mentions}\n\n"
                    f"**Referee:** {ref_mention}\n\n"
                    f"Report the final score using `/report_score match_id:{match_id} winner_id:{p1_id}/{p2_id} scores_csv:0-0`\n"
                    f"**Challonge:** <https://challonge.com/{tournament_id}>\n"
                    f"Good luck!",
                    # Allowed Mentions ensures only the explicit users/roles are pinged
                    allowed_mentions=discord.AllowedMentions(users=True, roles=[referee_role] if referee_role else False) 
                )
                
                # Store the thread ID
                data['match_threads'][match_id] = thread.id
                data['challonge_matches'][match_id] = match # Store match data
                
                new_threads_created += 1
                message_content += f"- **{thread_name}** (Match ID: `{match_id}`)\n"
                
            except Exception as e:
                message_content += f"- ❌ Failed to create thread for **{thread_name}**: {e}\n"
    
    save_data()

    if new_threads_created > 0:
        await interaction.followup.send(message_content)
    else:
        await interaction.followup.send("ℹ️ No new open matches found to create threads for. All available matches have threads or the tournament is complete.")


# /report_score <match_id> <winner_id> <score>
@client.tree.command(name="report_score", description="Report the score of a match and progress the tournament.")
@app_commands.describe(
    match_id="The Challonge Match ID (from the thread message).",
    winner_id="The participant ID of the winning team (Player 1/2 ID).",
    scores_csv="The score for both players, e.g., '2-1'"
)
async def report_score(interaction: discord.Interaction, match_id: int, winner_id: int, scores_csv: str):
    """Updates the match score on Challonge and checks for new matches."""
    await interaction.response.defer(ephemeral=True)
    
    # Optional: Check if the user is a referee or admin before allowing report
    if not (interaction.user.guild_permissions.manage_guild or interaction.user.get_role(REFEREE_ROLE_ID)):
         await interaction.followup.send("❌ You must be an administrator or have the Referee role to report scores.", ephemeral=True)
         return

    tournament_id = data.get('tournament_id')
    if not tournament_id:
        await interaction.followup.send("❌ No active tournament.")
        return

    match_id_str = str(match_id)
    
    # 1. Update Score on Challonge
    update_data = {
        "match": {
            "winner_id": winner_id,
            "scores_csv": scores_csv
        }
    }
    
    result, error = challonge_api_call('PUT', f"/{tournament_id}/matches/{match_id}", json_data=update_data)
    
    if error:
        await interaction.followup.send(f"❌ Error reporting score to Challonge: {error}. Did you use the correct winner ID?", ephemeral=True)
        return

    # 2. Notify in Thread and Clean Up
    thread_notification_sent = False
    if match_id_str in data['match_threads']:
        thread_id = data['match_threads'][match_id_str]
        thread = interaction.guild.get_channel(thread_id)
        if thread:
            # Get the winner's name for a nicer message
            participants_result, _ = challonge_api_call('GET', f"/{tournament_id}/participants")
            participant_map = {str(p['participant']['id']): p['participant']['name'] for p in participants_result}
            winner_name = participant_map.get(str(winner_id), f"ID:{winner_id}")

            await thread.send(
                f"✅ **MATCH COMPLETE!** Reported by {interaction.user.mention}.\n"
                f"**Winner:** {winner_name} with score **{scores_csv}**.\n"
                f"The next round match, if available, will be created shortly. Checking bracket progress..."
            )
            # Clean up local storage for the finished match
            del data['match_threads'][match_id_str] 
            data['challonge_matches'].pop(match_id_str, None)
            save_data()
            thread_notification_sent = True
    
    if thread_notification_sent:
        await interaction.followup.send("✅ Score reported successfully and match thread updated. Checking for next round matches...", ephemeral=True)
    else:
        await interaction.followup.send("✅ Score reported successfully to Challonge. No matching active thread was found for cleanup. Checking for next round matches...", ephemeral=True)
    
    # 3. Automatically check and create next round threads
    await create_threads(interaction) 


# /delete_tournament
@client.tree.command(name="delete_tournament", description="Deletes the current Challonge tournament and all related data/threads.")
async def delete_tournament(interaction: discord.Interaction):
    """Deletes the Challonge tournament, clears local data, and deletes threads."""
    await interaction.response.defer(ephemeral=True)

    tournament_id = data.get('tournament_id')
    if not tournament_id:
        await interaction.followup.send("❌ No active tournament to delete.")
        return

    # 1. Delete Threads
    deleted_count = 0
    channel = interaction.channel
    for thread_id in list(data['match_threads'].values()):
        try:
            thread = interaction.guild.get_channel(thread_id)
            if thread and isinstance(thread, discord.Thread):
                 await thread.delete()
                 deleted_count += 1
        except Exception as e:
            # Note: Discord bots can only delete threads they created
            print(f"Error deleting thread {thread_id}: {e}")
            
    # 2. Delete Challonge Tournament
    _, error = challonge_api_call('DELETE', f"/{tournament_id}")

    # 3. Clear Local Data (keep teams registration)
    data['tournament_id'] = None
    data['match_threads'] = {}
    data['challonge_matches'] = {}
    save_data()

    if error:
        await interaction.followup.send(
            f"⚠️ Local data cleared, {deleted_count} threads deleted, but **failed to delete Challonge tournament** `{tournament_id}`: {error}. You may need to delete it manually."
        )
    else:
        await interaction.followup.send(
            f"✅ Tournament `{tournament_id}` deleted from Challonge. "
            f"All {deleted_count} related match threads and local data have been cleared. **Teams remain registered.**"
        )

# --- RUN BOT ---
if __name__ == "__main__":
    if DISCORD_BOT_TOKEN:
        try:
            client.run(DISCORD_BOT_TOKEN)
        except discord.errors.LoginFailure:
            print("❌ Invalid Discord Bot Token. Please check your token in Replit Secrets.")
    else:
        print("❌ Cannot run bot: DISCORD_BOT_TOKEN is missing. Check Replit Secrets.")
