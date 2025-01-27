from botbuilder.core import ActivityHandler, MessageFactory, TurnContext
from botbuilder.schema import ChannelAccount, Attachment
import pandas as pd
from datetime import datetime, timedelta
import requests
from azure.identity import DefaultAzureCredential
import re
import calendar
import matplotlib.pyplot as plt
import io
import base64



class EchoBot(ActivityHandler):
    def __init__(self):
        self.credential = DefaultAzureCredential()
        self.endpoint = "https://subscriptioncost.openai.azure.com"
        self.deployment_id = "chatbot-deployment"

    async def on_members_added_activity(
            self, members_added: [ChannelAccount], turn_context: TurnContext
    ):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "Welcome to the Azure Subscription Cost Chatbot! Ask me about Azure costs.")

    async def on_message_activity(self, turn_context: TurnContext):
        user_input = turn_context.activity.text
        try:
            response_text = await self.handle_cost_query(user_input, turn_context)
            await turn_context.send_activity(MessageFactory.text(response_text))
        except Exception as e:
            await turn_context.send_activity(f"An error occurred: {str(e)}")

    async def handle_cost_query(self, query, turn_context):
        try:
            # Check for cost-related keywords
            if any(keyword in query.lower() for keyword in ["costs", "expenditure", "summarize", "spend"]):
                if "last six months" in query.lower():
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=180)
                elif "from" in query.lower() and "to" in query.lower():
                    start_date_str, end_date_str = self.extract_dates(query)
                    start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                    end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                elif "in" in query.lower():
                    month_year = self.extract_month_year(query)
                    start_date, end_date = self.get_month_date_range(month_year)
                elif "past week" in query.lower():
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=7)
                elif "this year" in query.lower():
                    start_date = datetime(datetime.now().year, 1, 1)
                    end_date = datetime.now()
                elif "last month" in query.lower():
                    end_date = datetime.now().replace(day=1) - timedelta(days=1)
                    start_date = end_date.replace(day=1)
                elif "q1" in query.lower() or "q2" in query.lower() or "q3" in query.lower() or "q4" in query.lower():
                    # Extract the quarter and year from the query
                    quarter, year = self.extract_quarter_year(query)
                    start_date, end_date = self.get_quarter_dates(quarter, int(year))
                elif "to" in query.lower():
                    quarters = re.findall(r"(Q[1-4]) (\d{4})", query)
                    if len(quarters) == 2:
                        start_quarter, start_year = quarters[0]
                        end_quarter, end_year = quarters[1]
                        start_date, _ = self.get_quarter_dates(start_quarter, int(start_year))
                        _, end_date = self.get_quarter_dates(end_quarter, int(end_year))
                        cost_data = self.get_cost_data(start_date, end_date)
                else:
                    raise ValueError(
                        "Please enter dates in the format 'YYYY-MM-DD to YYYY-MM-DD' or specify a month and year.")

                cost_data = self.get_cost_data(start_date, end_date)
                if "daily breakdown" in query.lower():
                    return self.format_daily_cost_data(cost_data)
                else:
                    return self.format_cost_data(cost_data)
            elif "compare" in query.lower():
                return await self.compare_costs(query, turn_context)
            else:
                # Route non-cost-related queries to OpenAI
                return await self.call_openai_api(query)
        except ValueError as ve:
            return str(ve)
        except Exception as e:
            return f"An error occurred: {str(e)}"

    def extract_dates(self, query):
        # Use regular expressions to find dates in the format 'YYYY-MM-DD'
        date_pattern = r'\d{4}-\d{2}-\d{2}'
        dates = re.findall(date_pattern, query)

        if len(dates) == 2:
            start_date_str, end_date_str = dates
            return start_date_str, end_date_str
        else:
            raise ValueError("Please enter dates in the format 'YYYY-MM-DD to YYYY-MM-DD'.")

    def extract_month_year(self, query):
        # Extract month and year from the query string
        words = query.split()
        month_year = None
        for i, word in enumerate(words):
            if word.capitalize() in calendar.month_name:
                # Remove any non-numeric characters from the year part
                year = ''.join(filter(str.isdigit, words[i + 1]))
                month_year = f"{words[i]} {year}"
                break
        if month_year:
            return month_year
        else:
            raise ValueError("Please specify a valid month and year.")

    def get_month_date_range(self, month_year):
        # Convert month and year to start and end dates
        month, year = month_year.split()
        month_num = list(calendar.month_name).index(month.capitalize())
        start_date = datetime(int(year), month_num, 1)
        end_date = datetime(int(year), month_num, calendar.monthrange(int(year), month_num)[1])
        return start_date, end_date

    def get_cost_data(self, start_date, end_date):
        try:
            credential = DefaultAzureCredential()
            subscription_id = '7b9338d2-e8dc-405b-91d7-ef8fe30b97b6'
            cost_management_url = f"https://management.azure.com/subscriptions/{subscription_id}/providers/Microsoft.CostManagement/query?api-version=2021-10-01"

            # Get the access token
            token = credential.get_token("https://management.azure.com/.default").token

            # Set the headers
            headers = {
                'Authorization': f'Bearer {token}',
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

            # Debugging statements
            print("URL:", cost_management_url)
            print("Headers:", headers)
            print("Query:", query)

            response = requests.post(cost_management_url, headers=headers, json=query)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()['properties']['rows']
        except Exception as e:
            raise Exception(f"Failed to retrieve cost data: {str(e)}")

    def format_cost_data(self, cost_data):
        # Extract relevant data and create a DataFrame
        data = []
        for item in cost_data:
            data.append({
                'Resource Group': item[2],
                'Date': item[1],
                'Cost': item[0]
            })

        df = pd.DataFrame(data)
        total_cost = df['Cost'].sum()
        return f"Total cost: ${total_cost:.2f}\n\n{df.to_string()}"

    def format_daily_cost_data(self, cost_data):
        # Extract relevant data and create a DataFrame
        data = []
        for item in cost_data:
            data.append({
                'Date': item[1],
                'Cost': item[0]
            })

        df = pd.DataFrame(data)
        return df.to_string()

    def get_quarter_dates(self, quarter, year):
        if quarter == "Q1":
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 3, 31)
        elif quarter == "Q2":
            start_date = datetime(year, 4, 1)
            end_date = datetime(year, 6, 30)
        elif quarter == "Q3":
            start_date = datetime(year, 7, 1)
            end_date = datetime(year, 9, 30)
        elif quarter == "Q4":
            start_date = datetime(year, 10, 1)
            end_date = datetime(year, 12, 31)
        return start_date, end_date

    def extract_quarter_year(self, query):
        # Example: "Q1 2025" -> ("Q1", "2025")
        match = re.search(r"(Q[1-4]) (\d{4})", query, re.IGNORECASE)
        if match:
            return match.groups()
        else:
            raise ValueError("Please provide a valid quarter and year, e.g., 'Q1 2025'.")

    async def compare_costs(self, query, turn_context):
        try:
            # Extract months and years from the query
            months_years = re.findall(r'([A-Za-z]+) (\d{4})', query)
            if len(months_years) != 2:
                raise ValueError("Please provide two valid month-year pairs, e.g., 'January 2024 to March 2024'.")

            # Extract the month and year values
            month1, year1 = months_years[0]
            month2, year2 = months_years[1]

            # Convert the month name to a number
            month1_num = list(calendar.month_name).index(month1.capitalize())
            month2_num = list(calendar.month_name).index(month2.capitalize())

            # Create datetime objects for the start and end dates of both periods
            start_date1 = datetime(int(year1), month1_num, 1)
            end_date1 = datetime(int(year1), month1_num, calendar.monthrange(int(year1), month1_num)[1])

            start_date2 = datetime(int(year2), month2_num, 1)
            end_date2 = datetime(int(year2), month2_num, calendar.monthrange(int(year2), month2_num)[1])

            # Fetch cost data for both periods
            cost_data1 = self.get_cost_data(start_date1, end_date1)
            cost_data2 = self.get_cost_data(start_date2, end_date2)

            total_cost1 = sum(item[0] for item in cost_data1)
            total_cost2 = sum(item[0] for item in cost_data2)

            # Create a bar graph to compare the costs
            periods = [f"{month1} {year1}", f"{month2} {year2}"]
            costs = [total_cost1, total_cost2]

            fig, ax = plt.subplots()
            ax.bar(periods, costs, color=['blue', 'green'])

            ax.set_xlabel('Periods')
            ax.set_ylabel('Total Cost ($)')
            ax.set_title('Cost Comparison')

            # Save the plot to a BytesIO object
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)

            # Create the image attachment
            attachment = Attachment(
                content_type="image/png",
                content_url="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')
            )

            # Send the image as an attachment
            await turn_context.send_activity(
                f"Here is the cost comparison graph between {month1} {year1} and {month2} {year2}:")
            await turn_context.send_activity(
                MessageFactory.attachment(attachment)
            )

            return f"Total cost for {month1} {year1}: ${total_cost1:.2f}\nTotal cost for {month2} {year2}: ${total_cost2:.2f}"

        except ValueError as ve:
            return str(ve)
        except Exception as e:
            return f"An error occurred: {str(e)}"



    async def call_openai_api(self, prompt):
        url = f"{self.endpoint}/openai/deployments/{self.deployment_id}/chat/completions?api-version=2024-06-01"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.credential.get_token('https://cognitiveservices.azure.com/.default').token}"
        }
        data = {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 150
        }
        try:
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as http_err:
            return f"HTTP error occurred: {http_err.response.text}"
        except Exception as err:
            return f"An error occurred: {str(err)}"
