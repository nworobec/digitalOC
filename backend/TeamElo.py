import pandas as pd
import numpy as np
import nflreadpy as nfl


#pd.read_csv("data/pbp_participation_2024.csv")
df0 = pd.read_csv("data/pbp_2020_0.csv", low_memory=False)
df1 = pd.read_csv("data/pbp_2020_1.csv", low_memory=False)

merged = pd.concat([df0, df1], ignore_index=True)


class PlayClassifier:
    @staticmethod
    def get_category(row):
        """
        Classify a play into a detailed offensive category.

        Categories include:
            - Special QB actions: qb_kneel, qb_spike, qb_scramble, sack
            - Pass types: screen_pass, short_pass, mid_pass, deep_pass
            - Run types: inside_run, outside_run
            - Fallbacks: pass, run, or other

        Parameters:
            row (pd.Series): A row from a play-by-play DataFrame.

        Returns:
            str: Play category label.
        """
        # ignore non‑offensive plays
        if row.get("play_type") not in ["pass", "run"]:
            return "other"

        # special QB situations
        if row.get("qb_kneel") == 1:
            return "qb_kneel"
        elif row.get("qb_spike") == 1:
            return "qb_spike"
        elif row.get("qb_scramble") == 1:
            return "qb_scramble"
        elif row.get("sack") == 1:
            return "sack"

     
        if row.get("pass_attempt") == 1:
            air_yards = row.get("air_yards")
            if pd.isna(air_yards):
                return "pass"
            try:
                air_yards = float(air_yards)
                if air_yards < 0:
                    return "screen_pass"
                elif air_yards <= 7:
                    return "short_pass"
                elif air_yards <= 15:
                    return "mid_pass"
                else:
                    return "deep_pass"
            except:
                return "pass"
            


        # --- RUN PLAYS ---
        elif row.get("rush_attempt") == 1:
            gap = str(row.get("run_gap")).lower() if pd.notna(row.get("run_gap")) else ""
            if gap in ["guard", "center"]:
                return "inside_run"
            elif gap == "end":
                return "outside_run"


        return "other"


        
class Team:
    def __init__(self, name: str, df: pd.DataFrame):
        """
        Initialize a Team object for filtering and calculating team-level stats.

        Parameters:
            name (str): Team abbreviation (e.g., "KC").
            df (pd.DataFrame): Full play-by-play dataset.
        """

        self.name = name
        self.df = df

    def offensive_snaps(self):
        """
        Count the number of offensive plays for the team.

        Returns:
            int: Number of unique offensive snaps (by play_id).
        """
        return self.df[self.df["posteam"] == self.name]["play_id"].nunique()

    def offensive_personnel_counts(self):
        """
        Count occurrences of each offensive personnel grouping used by the team.

        Returns:
            pd.Series: Personnel groupings with counts.
        """
        return self.df[self.df["posteam"] == self.name]["offense_personnel"].value_counts()

    def formation_counts(self):
        """
        Count the frequency of each offensive formation used by the team.

        Returns:
            pd.Series: Formation types with counts.
        """
        return self.df[self.df["posteam"] == self.name]["offense_formation"].value_counts()

    def defensive_personnel_faced(self):
        """
        Count defensive personnel groupings the team faced while on offense.

        Returns:
            pd.Series: Defensive personnel groupings with counts.
        """
        return self.df[self.df["posteam"] == self.name]["defense_personnel"].value_counts()

    def pressure_rate(self):
        """
        Compute the percentage of plays where the QB faced pressure.

        Returns:
            float: Pressure rate as a decimal (0 to 1).
        """

        return self.df[self.df["posteam"] == self.name]["was_pressure"].mean()
    
    @staticmethod
    def success_rule(row):
        """
        Determine if a play is successful based on down and yardage gained.

        Rules:
            - 1st down: gain at least 50% of yards-to-go
            - 2nd down: gain at least 70% of yards-to-go
            - 3rd/4th down: gain 100% of yards-to-go

        Parameters:
            row (pd.Series): A row from the play-by-play DataFrame.

        Returns:
            bool: True if the play is successful, False otherwise.
        """
        if row["down"] == 1:
            return row["yards_gained"] >= 0.5 * row["ydstogo"]
        elif row["down"] == 2:
            return row["yards_gained"] >= 0.7 * row["ydstogo"]
        elif row["down"] in [3, 4]:
            return row["yards_gained"] >= row["ydstogo"]
        return False

    
    def success_rate_by_down(self):
        """
        Calculate the play success rate for each down (1st to 4th).

        Returns:
            pd.Series: Success rate per down (index: down, value: rate).
        """
        df = self.df[self.df["posteam"] == self.name].copy()
        df = df.dropna(subset=["down", "yards_gained", "ydstogo"])

        df["successful"] = df.apply(self.success_rule, axis=1)

        rates = (
            df.groupby("down")["successful"]
            .mean()
            .round(3)
            .rename("success_rate")
        )

        return rates
    
    
    def success_rate_by_playType(self):
        """
        Calculate the success rate for each basic play type (run, pass).

        Returns:
            pd.Series: Success rate per play_type (e.g., pass, run).
        """
        df = self.df[self.df["posteam"] == self.name].copy()
        df = df.dropna(subset=["down", "yards_gained", "ydstogo"])

        df["successful"] = df.apply(self.success_rule, axis=1)

        rates = (
            df.groupby("play_type")["successful"]
            .mean()
            .round(3)
            .rename("success_rate")
        )

        return rates
    
    def playType_by_down(self):
        """
        Show the percentage distribution of play types used on each down.

        Returns:
            pd.DataFrame: Rows = down, Columns = play types, Values = percentages.
        """
        # Filter to this team's offensive plays
        df = self.df[self.df["posteam"] == self.name].copy()
        
        # Keep only rows with valid down and play_type
        df = df.dropna(subset=["down", "play_type"])
        
        # Count plays by down and play_type
        counts = df.groupby(["down", "play_type"]).size().unstack(fill_value=0)
        
        # Convert counts to percentages
        fractions = counts.div(counts.sum(axis=1), axis=0).round(3)
        
        return fractions
    
    def blitz_rate_by_down(self):
        """
        Calculate the rate of blitzes faced on each down when on defense.

        Returns:
            pd.Series: Blitz rate per down (0–1).
        """
        # Filter for plays where this team was on defense
        df = self.df[self.df["defteam"] == self.name].copy()

        # Keep only rows with valid down and number_of_pass_rushers
        df = df.dropna(subset=["down", "number_of_pass_rushers"])

        # Define a blitz
        df["blitz"] = df["number_of_pass_rushers"] > 4

        # Calculate blitz rate by down
        blitz_rates = (
            df.groupby("down")["blitz"]
            .mean()
            .round(3)
            .rename("blitz_rate")
        )

        return blitz_rates
    
    def success_against_blitz(self):
        """
        Measure offensive success against blitzes (defined as >4 rushers).

        A play is unsuccessful if:
            - Pressure was recorded
            - Yards gained was negative

        Returns:
            float: Success rate against blitzes (0–1).
        """
        df = self.df[self.df["posteam"] == self.name].copy()

        
        df = df.dropna(subset=["number_of_pass_rushers", "yards_gained", "was_pressure"])

        
        blitz_df = df[df["number_of_pass_rushers"] > 4]

        if blitz_df.empty:
            return 0.0  

       
        blitz_df["unsuccessful"] = (blitz_df["was_pressure"]) | (blitz_df["yards_gained"] < 0)

       
        success_ratio = 1 - blitz_df["unsuccessful"].mean()

        return round(success_ratio, 3)

    def offensive_category_stats(self):
        """
        Aggregate play-level metrics by detailed play category.

        Metrics:
            - Number of plays
            - Success rate
            - Average yards gained
            - Average EPA

        Returns:
            pd.DataFrame: Index = play_category, Columns = metrics.
        """
        df = self.df[self.df["posteam"] == self.name].copy()
        df = df.dropna(subset=["play_category", "yards_gained", "down", "ydstogo"])
        df["successful"] = df.apply(self.success_rule, axis=1)

        stats = (
            df.groupby("play_category")
            .agg(
                num_plays=("play_id", "count"),
                success_rate=("successful", "mean"),
                avg_yards=("yards_gained", "mean"),
                avg_epa=("epa", "mean")
            )
            .sort_values("num_plays", ascending=False)
            .round(3)
        )

        return stats

    


    

    def __repr__(self):
        """
        Return a string representation of the team with number of offensive snaps.

        Returns:
            str: Representation string.
        """
        return f"<Team {self.name}: {self.offensive_snaps()} offensive snaps>"

merged["play_category"] = merged.apply(PlayClassifier.get_category, axis=1)
def compute_elo_per_play_type(category_stats: pd.DataFrame) -> dict:
    """
    Compute a separate ELO-style score for each primary play category.
    Returns a dictionary: {category_name: elo_score}
    """
    # Define weights
    w_success = 0.4
    w_epa = 0.6

    elo_scores = {}

    # Only include relevant play types
    for category in ["deep_pass", "mid_pass", "short_pass", "screen_pass", "inside_run", "outside_run"]:
        if category in category_stats.index:
            row = category_stats.loc[category]
            success = row.get("success_rate", 0)
            epa = row.get("avg_epa", 0)

            # Normalize metrics
            norm_success = (success - 0.4) / (0.6 - 0.4)  # Assume success ~ 0.4 to 0.6
            norm_epa = (epa + 0.5) / 1.0                  # Assume EPA ~ -0.5 to +0.5

            
            norm_success = np.clip(norm_success, 0, 1)
            norm_epa = np.clip(norm_epa, 0, 1)

          
            elo = 1000 + 400 * (w_success * norm_success + w_epa * norm_epa)
            elo_scores[category] = round(elo, 2)
        else:
            elo_scores[category] = 1000.0  

    return elo_scores


# Build ELO for all teams
merged["play_category"] = merged.apply(PlayClassifier.get_category, axis=1)

team_elos = {}
for team in merged["posteam"].dropna().unique():
    t = Team(team, merged)
    stats = t.offensive_category_stats()
    team_elos[team] = compute_elo_per_play_type(stats)


elo_df = pd.DataFrame(team_elos).T  # Transpose so teams are rows

# Save to CSV in the data directory
elo_df.to_csv("data/team_elos_2020.csv", index_label="team")



        

