import os
import json
import logging
from datetime import datetime, timedelta
import requests
import pytz
import time
import random

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

        # Define correct query IDs for each metric
        self.QUERY_IDS = {
            'active_addresses': '1619273/2684507',  # Using the specific query for active addresses
            'contract_deployments': '1619273/2835668',  # Using the specific query for contract deployments
            'eth_burned': '1725751/2846212'  # Using the specific query for ETH burned
        }
        logger.info("DuneService initialized with API key and query IDs")

    def _retry_with_backoff(self, func, max_retries=5, base_delay=1):
        """Execute a function with exponential backoff retry logic"""
        for attempt in range(max_retries):
            try:
                return func()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit hit
                    if attempt == max_retries - 1:
                        raise
                    delay = min(300, (base_delay * (2 ** attempt)) + (random.random() * 2))
                    logger.warning(f"Rate limit hit, retrying in {delay} seconds (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise

    def _execute_query(self, query_id, params=None):
        """Execute a Dune query and return the results"""
        try:
            query_id_parts = query_id.split('/')
            if len(query_id_parts) != 2:
                raise ValueError(f"Invalid query ID format: {query_id}")

            query_id, execution_id = query_id_parts

            def execute_request():
                # Execute query
                execution_endpoint = f"{self.base_url}/query/{query_id}/execute"
                logger.info(f"Executing Dune query {query_id} with params: {params}")

                execution_response = requests.post(
                    execution_endpoint,
                    headers=self.headers,
                    json={"parameters": params or {}}
                )
                execution_response.raise_for_status()
                return execution_response.json().get('execution_id', execution_id)

            execution_id = self._retry_with_backoff(execute_request)
            logger.debug(f"Query {query_id} execution started with ID: {execution_id}")

            def get_results():
                results_endpoint = f"{self.base_url}/execution/{execution_id}/results"
                results_response = requests.get(results_endpoint, headers=self.headers)
                results_response.raise_for_status()
                return results_response.json()

            # Poll for results with backoff
            max_attempts = 10
            for attempt in range(max_attempts):
                try:
                    result_data = self._retry_with_backoff(get_results)
                    if result_data['state'] == 'QUERY_STATE_COMPLETED':
                        logger.info(f"Query {query_id} completed successfully")
                        logger.debug(f"Query {query_id} results: {json.dumps(result_data['result']['rows'], indent=2)}")
                        return result_data['result']['rows']
                    elif result_data['state'] in ['QUERY_STATE_FAILED', 'QUERY_STATE_CANCELLED']:
                        error_msg = f"Query failed with state: {result_data['state']}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = min(60, 2 ** attempt)
                    logger.info(f"Waiting {delay} seconds before next attempt...")
                    time.sleep(delay)

            raise Exception("Maximum polling attempts reached")

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

            logger.info(f"Fetching metrics for period: {start_str} to {end_str}")

            # Fetch metrics using the specified query IDs
            logger.info("Fetching active addresses data...")
            active_addresses = self._execute_query(self.QUERY_IDS['active_addresses'], params)

            logger.info("Fetching contract deployments data...")
            contract_deployments = self._execute_query(self.QUERY_IDS['contract_deployments'], params)

            logger.info("Fetching ETH burned data...")
            eth_burned = self._execute_query(self.QUERY_IDS['eth_burned'], params)

            # Process and structure the data
            metrics = {
                'active_addresses': self._process_daily_data(active_addresses),
                'contracts_deployed': self._process_daily_data(contract_deployments),
                'eth_burned': sum(float(row['amount']) for row in eth_burned) if eth_burned else 0
            }

            logger.info(f"Successfully fetched and processed metrics: {json.dumps(metrics, indent=2)}")
            return metrics

        except Exception as e:
            logger.error(f"Error fetching weekly metrics: {str(e)}")
            raise

    def _process_daily_data(self, data):
        """Convert daily metrics into a structured format"""
        try:
            if not data:
                logger.warning("No data received for processing")
                return {}

            processed = {row['date']: int(row['value']) for row in data}
            logger.debug(f"Processed daily data: {json.dumps(processed, indent=2)}")
            return processed
        except Exception as e:
            logger.error(f"Error processing daily data: {str(e)}")
            raise