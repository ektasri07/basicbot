from botbuilder.core import ActivityHandler, MessageFactory, TurnContext
from botbuilder.schema import ChannelAccount
import pandas as pd
from datetime import datetime
import requests
from azure.identity import DefaultAzureCredential

class EchoBot(ActivityHandler):
    async def on_members_added_activity(
        self, members_added: [ChannelAccount], turn_context: TurnContext
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Welcome to the Azure Subscription Cost Chatbot! Ask me about Azure costs.")

    async def on_message_activity(self, turn_context: TurnContext):
        user_input = turn_context.activity.text
        try:
            start_date_str, end_date_str = user_input.split(" to ")
            start_date = datetime.strptime(start_date_str.strip(), '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str.strip(), '%Y-%m-%d')

            cost_data = self.get_cost_data(start_date, end_date)

            # Extract relevant data and create a DataFrame
            data = []
            for item in cost_data['properties']['rows']:
                data.append({
                    'Resource Group': item[2],
                    'Date': item[1],
                    'Cost': item[0]
                })

            df = pd.DataFrame(data)
            await turn_context.send_activity(MessageFactory.text(df.to_string()))
        except ValueError:
            await turn_context.send_activity("Please enter dates in the format 'YYYY-MM-DD to YYYY-MM-DD'.")
        except Exception as e:
            await turn_context.send_activity(f"An error occurred: {str(e)}")

    def get_cost_data(self, start_date, end_date):
        try:
            credential = DefaultAzureCredential()
            subscription_id = '7b9338d2-e8dc-405b-91d7-ef8fe30b97b6'
            cost_management_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2021-10-01"

            headers = {
                'Authorization': f'Bearer {credential.get_token("https://management.azure.com/.default").token}',
                'Content-Type': 'application/json'
            }

            # Convert date objects to strings
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')

            query = {
                "type": "Usage",
                "timeframe": "Custom",
                "timePeriod": {
                    "from": start_date_str,
                    "to": end_date_str
                },
                "dataset": {
                    "granularity": "Daily",
                    "aggregation": {
                        "totalCost": {
                            "name": "Cost",
                            "function": "Sum"
                        }
                    },
                    "grouping": [
                        {
                            "type": "Dimension",
                            "name": "ResourceGroupName"
                        }
                    ]
                }
            }

            response = requests.post(cost_management_url, headers=headers, json=query)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()
        except Exception as e:
            raise Exception(f"Failed to retrieve cost data: {str(e)}")