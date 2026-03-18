"""
driftlock-guardrail-assistant.py
Scenario 02 — Query Guardrails

Lambda function that orchestrates the full query pipeline:
    User query → Bedrock Guardrail → Knowledge Base → Response

Guardrail intervention is detected using three methods:
    1. guardrailAction field in API response
    2. Redirect message pattern matching
    3. Missing citations combined with short response

Blocked queries publish a BlockedQueries metric to CloudWatch
for the driftlock-reconnaissance-alarm to evaluate.

IAM Role: driftlock-guardrail-assistant-role
Timeout:  60 seconds (Bedrock calls can take 10-30 seconds)

Production notes:
    - Update GUARDRAIL_ID with actual guardrail ID
    - Update YOUR_KNOWLEDGE_BASE_ID with actual knowledge base ID
    - WAF attachment to API Gateway recommended for production
    - SNS notification on alarm recommended for production
"""

import boto3
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

KNOWLEDGE_BASE_ID = 'YOUR_KNOWLEDGE_BASE_ID'
MODEL_ARN = 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0'
GUARDRAIL_ID = 'your-guardrail-id'
GUARDRAIL_VERSION = 'DRAFT'

REDIRECT_MESSAGE = (
    "I'm here to help with your research questions. "
    "Please try rephrasing your question and I will "
    "do my best to assist you."
)


def publish_blocked_metric():
    """
    Publishes a BlockedQueries count metric to CloudWatch.
    The driftlock-reconnaissance-alarm monitors this metric
    and triggers when 3 or more blocks occur within 3 minutes.
    """
    try:
        cloudwatch.put_metric_data(
            Namespace='DriftLock/QueryGuardrails',
            MetricData=[
                {
                    'MetricName': 'BlockedQueries',
                    'Value': 1,
                    'Unit': 'Count',
                    'Dimensions': [
                        {
                            'Name': 'Scenario',
                            'Value': 'scenario-02-query-guardrails'
                        }
                    ]
                }
            ]
        )
        logger.info("BlockedQueries metric published to CloudWatch")
    except Exception as e:
        logger.error(f"Failed to publish metric: {str(e)}")


def detect_guardrail_intervention(response, output_text):
    """
    Detects whether the Bedrock Guardrail intervened on the query.

    Uses three independent detection methods because the guardrailAction
    field is not consistently populated in all Bedrock API responses.

    Method 1 — API response field: Most reliable when populated.
    Method 2 — Redirect message: Catches what Method 1 misses.
    Method 3 — Missing citations: Approved responses always have citations.
    """
    # Method 1 — Check guardrailAction field directly
    if response.get('guardrailAction') == 'GUARDRAIL_INTERVENED':
        logger.info("Intervention detected via guardrailAction field")
        return 'INTERVENED'

    # Method 2 — Check response text matches redirect message pattern
    if output_text and output_text.strip().startswith(
        "I'm here to help with your research questions"
    ):
        logger.info("Intervention detected via redirect message pattern")
        return 'INTERVENED'

    # Method 3 — No citations combined with short response
    # Approved responses always include knowledge base citations
    # Blocked responses have neither citations nor long content
    citations = response.get('citations', [])
    if not citations and len(output_text) < 200:
        logger.info("Intervention detected via missing citations pattern")
        return 'INTERVENED'

    return 'NONE'


def lambda_handler(event, context):
    """
    Main handler supporting both direct Lambda invocation
    and API Gateway proxy integration.

    Expected event format (direct):
        {"query": "What are AI governance frameworks?"}

    Expected event format (API Gateway):
        {"body": "{\"query\": \"What are AI governance frameworks?\"}"}
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # Extract query from event
    try:
        if 'body' in event:
            # API Gateway proxy request
            body = json.loads(event['body']) \
                if isinstance(event['body'], str) \
                else event['body']
            query = body.get('query', '')
        else:
            # Direct Lambda invocation
            query = event.get('query', '')

        if not query:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "Query is required",
                    "message": "Please provide a query field"
                })
            }

    except Exception as e:
        logger.error(f"Failed to parse request: {str(e)}")
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "Invalid request format"
            })
        }

    logger.info(f"Processing query: {query}")

    # Query Bedrock Knowledge Base with Guardrail applied
    try:
        response = bedrock.retrieve_and_generate(
            input={
                'text': query
            },
            retrieveAndGenerateConfiguration={
                'type': 'KNOWLEDGE_BASE',
                'knowledgeBaseConfiguration': {
                    'knowledgeBaseId': KNOWLEDGE_BASE_ID,
                    'modelArn': MODEL_ARN,
                    'generationConfiguration': {
                        'guardrailConfiguration': {
                            'guardrailId': GUARDRAIL_ID,
                            'guardrailVersion': GUARDRAIL_VERSION
                        }
                    }
                }
            }
        )

        output_text = response['output']['text']

        # Detect guardrail intervention using three methods
        guardrail_action = detect_guardrail_intervention(
            response, output_text
        )

        if guardrail_action == 'INTERVENED':
            logger.warning(
                f"Guardrail intervened on query: {query}"
            )
            publish_blocked_metric()

            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json"
                },
                "body": json.dumps({
                    "response": output_text,
                    "guardrail_action": "INTERVENED",
                    "query_processed": True
                })
            }

        logger.info("Query responded successfully")

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "response": output_text,
                "guardrail_action": "NONE",
                "query_processed": True
            })
        }

    except Exception as e:
        logger.error(f"Bedrock query failed: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "error": "Query processing failed",
                "message": str(e)
            })
        }
