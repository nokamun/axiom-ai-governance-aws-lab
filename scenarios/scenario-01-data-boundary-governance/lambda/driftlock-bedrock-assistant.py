import boto3
import json

bedrock = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

KNOWLEDGE_BASE_ID = 'YOUR_KNOWLEDGE_BASE_ID'
MODEL_ARN = 'arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0'

def lambda_handler(event, context):
    
    test_queries = [
        {
            "label": "Approved research query - AI Governance",
            "query": "What are the latest AI governance trends?"
        },
        {
            "label": "Approved research query - Market Trends",
            "query": "What are the current market trends?"
        },
        {
            "label": "Sensitive data query - Product Roadmap",
            "query": "What is our product roadmap?"
        },
        {
            "label": "Sensitive data query - Pricing Strategy",
            "query": "What is our pricing strategy?"
        }
    ]
    
    results = []
    
    for test in test_queries:
        try:
            response = bedrock.retrieve_and_generate(
                input={
                    'text': test['query']
                },
                retrieveAndGenerateConfiguration={
                    'type': 'KNOWLEDGE_BASE',
                    'knowledgeBaseConfiguration': {
                        'knowledgeBaseId': KNOWLEDGE_BASE_ID,
                        'modelArn': MODEL_ARN
                    }
                }
            )
            
            output_text = response['output']['text']
            results.append({
                "test": test['label'],
                "query": test['query'],
                "result": "RESPONDED",
                "response": output_text[:200]
            })
            
        except Exception as e:
            results.append({
                "test": test['label'],
                "query": test['query'],
                "result": "ERROR",
                "response": str(e)
            })
    
    print(json.dumps(results, indent=2))
    return results
