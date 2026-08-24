from apscheduler.schedulers.background import BackgroundScheduler

# Single shared scheduler for the whole process: MockProvider uses it to simulate call
# progression, and main.py registers the polling reconciler job on it. Started in main.py's
# lifespan (or explicitly in tests) and shut down on exit.
scheduler = BackgroundScheduler()
