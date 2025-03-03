import configparser
import argparse
import logging

import pandas

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
logger.addHandler(handler)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

CANVAS_LOGIN_ID_NAME = "SIS Login ID"


def load_canvas_grades(canvas_grades_file: str) -> pandas.DataFrame:
    df = pandas.read_csv(canvas_grades_file)
    logger.debug(df.head())
    return df


def load_mitx_grades(
    mitx_grades_file: str, assignment_names: list[str], assignment_max_scores: list[int]
) -> pandas.DataFrame:
    raw_data = pandas.read_csv(mitx_grades_file).convert_dtypes(convert_string=False)
    df = pandas.DataFrame()
    df["user_id"] = raw_data["user_id"]
    df["username"] = raw_data["username"].apply(lambda x: x + "@mit.edu")
    df["a1_grade"] = raw_data["grade-" + assignment_names[0]].apply(
        lambda x: x / assignment_max_scores[0]
    )
    df["a3_grade"] = raw_data["grade-" + assignment_names[1]].apply(
        lambda x: x / assignment_max_scores[1]
    )
    df["a7_grade"] = raw_data["grade-" + assignment_names[2]].apply(
        lambda x: x / assignment_max_scores[2]
    )
    df.fillna(0, inplace=True)
    logger.debug(df.head())
    return df


def load_groups(groups_file: str, non_data_rows: int = 5) -> pandas.DataFrame:
    def to_lower(x: str) -> str:
        try:
            return x.lower()
        except AttributeError:
            return x

    raw_df = pandas.read_csv(groups_file, skiprows=non_data_rows)
    df = pandas.DataFrame()
    df.index = raw_df["Team Number"]
    df["Member 1"] = raw_df["E-mail (1st Member)"].apply(to_lower)
    df["Member 2"] = raw_df["E-mail (2nd Member)"].apply(to_lower)
    df["Member 3"] = raw_df["E-mail (3rd Member)"].apply(to_lower)
    logger.debug(df.head())
    return df


def load_mitx_into_groups(
    mitx_df: pandas.DataFrame, groups_df: pandas.DataFrame
) -> pandas.DataFrame:
    def calculate_score(row: pandas.Series, grade: str) -> float:
        try:
            score_1 = mitx_df[grade][mitx_df["username"] == row["Member 1"]].iloc[0]
        except IndexError:
            score_1 = 0
        try:
            score_2 = mitx_df[grade][mitx_df["username"] == row["Member 2"]].iloc[0]
        except IndexError:
            score_2 = 0
        try:
            score_3 = mitx_df[grade][mitx_df["username"] == row["Member 3"]].iloc[0]
        except IndexError:
            score_3 = 0
        return max(score_1, score_2, score_3)

    df = groups_df.copy()
    df["a3_score"] = df.apply(lambda x: calculate_score(x, "a3_grade"), axis=1)
    df["a7_score"] = df.apply(lambda x: calculate_score(x, "a7_grade"), axis=1)
    logger.debug(df.head())
    return df


def load_groups_into_canvas(
    groups_df: pandas.DataFrame,
    canvas_df: pandas.DataFrame,
    canvas_assignment_name: str,
    group_assignment_name: str,
) -> pandas.DataFrame:
    def find_score(row: pandas.Series, grade: str) -> float:

        if any(row[CANVAS_LOGIN_ID_NAME] == groups_df["Member 1"]):
            res = groups_df[row[CANVAS_LOGIN_ID_NAME] == groups_df["Member 1"]]
        elif any(row[CANVAS_LOGIN_ID_NAME] == groups_df["Member 2"]):
            res = groups_df[row[CANVAS_LOGIN_ID_NAME] == groups_df["Member 2"]]
        elif any(row[CANVAS_LOGIN_ID_NAME] == groups_df["Member 3"]):
            res = groups_df[row[CANVAS_LOGIN_ID_NAME] == groups_df["Member 3"]]
        else:
            logger.warning(
                f"Could not find student {row[CANVAS_LOGIN_ID_NAME]} ({row['Student']}) in groups"
            )
            return 0
        return round(res[grade].iloc[0] * 10, 1)

    df = canvas_df.copy()
    df[canvas_assignment_name].iloc[2:] = df.iloc[2:].apply(
        lambda x: find_score(x, group_assignment_name), axis=1
    )
    logger.debug(df.head())
    return df


def load_a1_into_canvas(
    mitx_df: pandas.DataFrame,
    canvas_df: pandas.DataFrame,
    canvas_assignment_name: str,
    mitx_assignment_name: str,
) -> pandas.DataFrame:
    mitx_assignment_name = "grade-" + mitx_assignment_name

    def find_score(row: pandas.Series) -> float:
        try:
            return mitx_df["a1_grade"][
                mitx_df["username"] == row[CANVAS_LOGIN_ID_NAME]
            ].iloc[0]
        except IndexError:
            logger.warning(
                f"Could not find student {row[CANVAS_LOGIN_ID_NAME]} ({row['Student']}) in mitx"
            )
            return 0

    df = canvas_df.copy()
    df[canvas_assignment_name].iloc[2:] = df.iloc[2:].apply(find_score, axis=1)
    logger.debug(df.head())
    return df


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mitx_assignment",
        type=int,
        help="The assignment number for the mitx grades",
        choices=[1, 3, 7],
    )
    args = parser.parse_args()
    return args


def main():
    config = configparser.ConfigParser()
    config.read("config.ini")
    args = get_args()

    canvas_grades = load_canvas_grades(config["FILES"]["canvas_grades"])
    mitx_name = argparse.ArgumentParser()
    mitx_name.add_argument("mitx_grades", type=str)
    mitx_grades = load_mitx_grades(
        config["FILES"]["mitx_grades"],
        assignment_names=[
            config["MITX"]["a1_name"],
            config["MITX"]["a3_name"],
            config["MITX"]["a7_name"],
        ],
        assignment_max_scores=[
            int(config["MITX"]["a1_max"]),
            int(config["MITX"]["a3_max"]),
            int(config["MITX"]["a7_max"]),
        ],
    )
    groups = load_groups(config["FILES"]["groups"])
    groups = load_mitx_into_groups(mitx_grades, groups)
    canvas_grades = load_a1_into_canvas(
        mitx_grades,
        canvas_grades,
        config["CANVAS"]["a1_name"],
        config["MITX"]["a1_name"],
    )
    canvas_grades = load_groups_into_canvas(
        groups, canvas_grades, config["CANVAS"]["a3_name"], "a3_score"
    )
    canvas_grades.to_csv("output.csv", index=False)


if __name__ == "__main__":
    main()
