import boto3, time

ssm = boto3.client('ssm', region_name='us-east-1')
r = ssm.send_command(
    InstanceIds=['i-0121b5db6d5159b30'],
    DocumentName='AWS-RunShellScript',
    Parameters={'commands': [
        'curl -s -o /dev/null -w "%{http_code}" http://localhost:8002/health',
        'echo "---"',
        'tail -n 20 /var/log/document-service.log',
        'echo "---"',
        'tail -n 20 /var/log/health-service.log'
    ]}
)
time.sleep(8)
out = ssm.get_command_invocation(
    CommandId=r['Command']['CommandId'],
    InstanceId='i-0121b5db6d5159b30'
)
print(out['StandardOutputContent'])
print("ERRORS:", out.get('StandardErrorContent', ''))
