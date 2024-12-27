# tools.py

from duckduckgo_search import DDGS

def search_tool(query: str) -> list:
    """
    Perform a web search using DuckDuckGo and return relevant results.

    Args:
        query (str): The search query string to look up information about.

    Returns:
        list: A list of dictionaries containing search results with the following keys:
            - title (str): The title of the search result
            - url (str): The URL of the search result
            - snippet (str): A brief excerpt or description of the search result
    """
    try:
        results = []
        ddgs = DDGS()
        for result in ddgs.text(keywords=query, max_results=10):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", ""),
            })
        return results

    except Exception as e:
        print(f"Error during DuckDuckGo search: {e}")
        return []

# # Define tools
# search_tool = {
#     "type": "function",
#     "function": {
#         "name": "search_tool",
#         "description": "Use this to perform search queries",
#         "parameters": {
#             "type": "object",
#             "properties": {
#                 "query": {"type": "string"},
#             },
#             "required": ["query"],
#         },
#     },
# }


# from duckduckgo_search import DDGS
# from praisonai_tools import BaseTool
# class InternetSearchTool(BaseTool):
#     name: str = "InternetSearchTool"
#     description: str = "Search Internet for relevant information based on a query or latest news"

#     def _run(self, query: str):
#         ddgs = DDGS()
#         results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
#         return results

# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build
# from google.auth.transport.requests import Request
# from google_auth_oauthlib.flow import Flow
# from google_auth_oauthlib.flow import InstalledAppFlow
# import os
# import json
# import webbrowser
# from http.server import HTTPServer, BaseHTTPRequestHandler
# from urllib.parse import urlparse, parse_qs
# import threading
# from datetime import datetime, timedelta
# import logging

# # Set up logging
# log_level = os.getenv('LOGLEVEL', 'INFO').upper()
# logging.basicConfig(level=log_level)
# logger = logging.getLogger(__name__)
# logger.setLevel(log_level)

# # Set up Google Calendar API
# SCOPES = ['https://www.googleapis.com/auth/calendar']

# def get_calendar_service():
#     logger.debug("Getting calendar service")
#     creds = None
#     token_dir = os.path.join(os.path.expanduser('~'), '.praison')
#     token_path = os.path.join(token_dir, 'token.json')
#     credentials_path = os.path.join(os.getcwd(), 'credentials.json')

#     if os.path.exists(token_path):
#         creds = Credentials.from_authorized_user_file(token_path, SCOPES)
#         logger.debug(f"Credentials loaded from {token_path}")

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             logger.debug(f"Refreshing credentials")
#             creds.refresh(Request())
#         else:
#             logger.debug(f"Starting new OAuth 2.0 flow")
#             flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
#             logger.debug(f"Credentials path: {credentials_path}")
#             creds = flow.run_local_server(port=8090)
#             logger.debug(f"Setting up flow from {credentials_path}")
#             # creds = flow.run_local_server(port=8090)  # Use run_local_server from InstalledAppFlow

#         # Ensure the ~/.praison directory exists
#         os.makedirs(os.path.dirname(token_path), exist_ok=True)
#         logger.debug(f"Saving credentials to {token_path}")
#         with open(token_path, 'w') as token:
#             token.write(creds.to_json())

#     logger.debug("Building calendar service")
#     return build('calendar', 'v3', credentials=creds)


# check_calendar_def = {
#     "name": "check_calendar",
#     "description": "Check Google Calendar for events within a specified time range",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "start_time": {"type": "string", "description": "Start time in ISO format (e.g., '2023-04-20T09:00:00-07:00')"},
#             "end_time": {"type": "string", "description": "End time in ISO format (e.g., '2023-04-20T17:00:00-07:00')"}
#         },
#         "required": ["start_time", "end_time"]
#     }
# }

# async def check_calendar_handler(start_time, end_time):
#     try:
#         service = get_calendar_service()
#         events_result = service.events().list(calendarId='primary', timeMin=start_time,
#                                               timeMax=end_time, singleEvents=True,
#                                               orderBy='startTime').execute()
#         events = events_result.get('items', [])
#         logger.debug(f"Found {len(events)} events in the calendar")
#         logger.debug(f"Events: {events}")
#         return json.dumps(events)
#     except Exception as e:
#         return {"error": str(e)}

# check_calendar = (check_calendar_def, check_calendar_handler)

# add_calendar_event_def = {
#     "name": "add_calendar_event",
#     "description": "Add a new event to Google Calendar",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "summary": {"type": "string", "description": "Event title"},
#             "start_time": {"type": "string", "description": "Start time in ISO format"},
#             "end_time": {"type": "string", "description": "End time in ISO format"},
#             "description": {"type": "string", "description": "Event description"}
#         },
#         "required": ["summary", "start_time", "end_time"]
#     }
# }

# async def add_calendar_event_handler(summary, start_time, end_time, description=""):
#     try:
#         service = get_calendar_service()
#         event = {
#             'summary': summary,
#             'description': description,
#             'start': {'dateTime': start_time, 'timeZone': 'UTC'},
#             'end': {'dateTime': end_time, 'timeZone': 'UTC'},
#         }
#         event = service.events().insert(calendarId='primary', body=event).execute()
#         logger.debug(f"Event added: {event}")
#         return {"status": "success", "event_id": event['id']}
#     except Exception as e:
#         return {"error": str(e)}

# add_calendar_event = (add_calendar_event_def, add_calendar_event_handler)

# list_calendar_events_def = {
#     "name": "list_calendar_events",
#     "description": "List Google Calendar events for a specific date",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "date": {"type": "string", "description": "Date in YYYY-MM-DD format"}
#         },
#         "required": ["date"]
#     }
# }

# async def list_calendar_events_handler(date):
#     try:
#         service = get_calendar_service()
#         start_of_day = f"{date}T00:00:00Z"
#         end_of_day = f"{date}T23:59:59Z"
#         events_result = service.events().list(calendarId='primary', timeMin=start_of_day,
#                                               timeMax=end_of_day, singleEvents=True,
#                                               orderBy='startTime').execute()
#         events = events_result.get('items', [])
#         logger.debug(f"Found {len(events)} events in the calendar for {date}")
#         logger.debug(f"Events: {events}")
#         return json.dumps(events)
#     except Exception as e:
#         return {"error": str(e)}

# list_calendar_events = (list_calendar_events_def, list_calendar_events_handler)

# update_calendar_event_def = {
#     "name": "update_calendar_event",
#     "description": "Update an existing Google Calendar event",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "event_id": {"type": "string", "description": "ID of the event to update"},
#             "summary": {"type": "string", "description": "New event title"},
#             "start_time": {"type": "string", "description": "New start time in ISO format"},
#             "end_time": {"type": "string", "description": "New end time in ISO format"},
#             "description": {"type": "string", "description": "New event description"}
#         },
#         "required": ["event_id"]
#     }
# }

# async def update_calendar_event_handler(event_id, summary=None, start_time=None, end_time=None, description=None):
#     try:
#         service = get_calendar_service()
#         event = service.events().get(calendarId='primary', eventId=event_id).execute()
        
#         if summary:
#             event['summary'] = summary
#         if description:
#             event['description'] = description
#         if start_time:
#             event['start'] = {'dateTime': start_time, 'timeZone': 'UTC'}
#         if end_time:
#             event['end'] = {'dateTime': end_time, 'timeZone': 'UTC'}
        
#         updated_event = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
#         logger.debug(f"Event updated: {updated_event}")
#         return {"status": "success", "updated_event": updated_event}
#     except Exception as e:
#         return {"error": str(e)}

# update_calendar_event = (update_calendar_event_def, update_calendar_event_handler)

# delete_calendar_event_def = {
#     "name": "delete_calendar_event",
#     "description": "Delete a Google Calendar event",
#     "parameters": {
#         "type": "object",
#         "properties": {
#             "event_id": {"type": "string", "description": "ID of the event to delete"}
#         },
#         "required": ["event_id"]
#     }
# }

# async def delete_calendar_event_handler(event_id):
#     try:
#         service = get_calendar_service()
#         service.events().delete(calendarId='primary', eventId=event_id).execute()
#         logger.debug(f"Event deleted: {event_id}")
#         return {"status": "success", "message": f"Event with ID {event_id} has been deleted"}
#     except Exception as e:
#         return {"error": str(e)}

# delete_calendar_event = (delete_calendar_event_def, delete_calendar_event_handler)



# tools = [
#     check_calendar,
#     add_calendar_event,
#     list_calendar_events,
#     update_calendar_event,
#     delete_calendar_event,
# ]

# # Add this to the imports at the top of the file if not already present
# from datetime import datetime

# # Add this new tool definition and handler
# contract_expiry_checker_def = {
#     "name": "check_contract_expiry",
#     "description": "Check the expiry date of the contract",
#     "parameters": {
#         "type": "object",
#         "properties": {},
#         "required": []
#     }
# }

# async def check_contract_expiry_handler():
#     # In a real-world scenario, this would likely query a database or API
#     # For this example, we'll return a fixed date
#     expiry_date = datetime(2024, 12, 10).strftime("%d %B %Y")
#     return {"expiry_date": expiry_date, "message": f"The contract expiry date is {expiry_date}."}

# check_contract_expiry = (contract_expiry_checker_def, check_contract_expiry_handler)

# # Add this to the tools list at the bottom of the file
# tools = [
#     check_calendar,
#     add_calendar_event,
#     list_calendar_events,
#     update_calendar_event,
#     delete_calendar_event,
#     check_contract_expiry,  # Add this line
# ]
