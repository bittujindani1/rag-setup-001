import datetime



import datetime

# Generate a unique assistant_id using the current date, time
def generate_id(name: str) -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    return f"{name}_{timestamp}"
