import os
import json
import logging
from datetime import datetime, timedelta
import requests
import pytz

logger = logging.getLogger(__name__)

class DuneService:
    def __init__(self):
        self.api_key = os.environ.get('DUNE_API_KEY')
        if not self.api_key:
            raise ValueError("DUNE_API_KEY environment variable is not set")

        self.base_url = "https://api.dune.com/api/v1"
        self.headers = {
            "x-dune-api-key": self.api_key,
            "Content-Type": "application/json"
        }

        # Define query IDs from the dashboard
        self.QUERY_IDS = {
            'active_addresses': '1619273',
            'contract_deployments': '1619273',
            'eth_burned': '1725751'
        }

    def _execute_query(self, query_id, params=None):
        """Execute a Dune query and return the results"""
        try:
            # Execute query
            execution_endpoint = f"{self.base_url}/query/{query_id}/execute"
            execution_response = requests.post(
                execution_endpoint,
                headers=self.headers,
                json={"parameters": params or {}}
            )
            execution_response.raise_for_status()
            execution_id = execution_response.json()['execution_id']

            # Get results
            results_endpoint = f"{self.base_url}/execution/{execution_id}/results"
            while True:
                results_response = requests.get(results_endpoint, headers=self.headers)
                results_response.raise_for_status()
                result_data = results_response.json()

                if result_data['state'] == 'QUERY_STATE_COMPLETED':
                    return result_data['result']['rows']
                elif result_data['state'] in ['QUERY_STATE_FAILED', 'QUERY_STATE_CANCELLED']:
                    raise Exception(f"Query failed with state: {result_data['state']}")

        except Exception as e:
            logger.error(f"Error executing Dune query {query_id}: {str(e)}")
            raise

    def get_weekly_metrics(self, start_date, end_date):
        """
        Fetch all required metrics for a given week
        Returns structured data ready to be stored in WeeklyMetrics
        """
        try:
            # Format dates for Dune queries
            start_str = start_date.strftime('%Y-%m-%d')
            end_str = end_date.strftime('%Y-%m-%d')

            params = {
                "start_date": start_str,
                "end_date": end_str
            }

            # Fetch metrics using the specified query IDs
            active_addresses = self._execute_query(self.QUERY_IDS['active_addresses'], params)
            contract_deployments = self._execute_query(self.QUERY_IDS['contract_deployments'], params)
            eth_burned = self._execute_query(self.QUERY_IDS['eth_burned'], params)

            # Process and structure the data
            metrics = {
                'active_addresses': self._process_daily_data(active_addresses),
                'contract_deployments': self._process_daily_data(contract_deployments),
                'eth_burned': sum(float(row['amount']) for row in eth_burned)
            }

            return metrics

        except Exception as e:
            logger.error(f"Error fetching weekly metrics: {str(e)}")
            raise

    def _process_daily_data(self, data):
        """Convert daily metrics into a structured format"""
        return {row['date']: row['value'] for row in data}