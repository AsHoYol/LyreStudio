import os

SCORES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scores")


def ensure_scores_dir():
    os.makedirs(SCORES_DIR, exist_ok=True)


def list_scores():
    ensure_scores_dir()
    return sorted(
        f for f in os.listdir(SCORES_DIR)
        if f.lower().endswith(".txt")
    )


def search_scores(keyword):
    keyword = keyword.strip().lower()
    files = list_scores()
    if not keyword:
        return files
    return [f for f in files if keyword in f.lower()]


def score_path(filename):
    return os.path.join(SCORES_DIR, filename)


def load_tokens(filename):
    path = score_path(filename)
    with open(path, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                lines.append(line)
    return " ".join(lines).split()


def display_name(filename):
    if filename and filename.lower().endswith(".txt"):
        return filename[:-4]
    return filename


def ensure_txt(name):
    name = name.strip()
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name