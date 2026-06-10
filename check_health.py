import boto3

elbv2 = boto3.client('elbv2', region_name='us-east-1')
tgs = elbv2.describe_target_groups()['TargetGroups']
frontend_tg = next(tg for tg in tgs if tg['TargetGroupName'] == 'medilink-frontend-tg')
health = elbv2.describe_target_health(TargetGroupArn=frontend_tg['TargetGroupArn'])
print('Frontend TG Health:')
for h in health['TargetHealthDescriptions']:
    print(f"{h['Target']['Id']}: {h['TargetHealth']['State']} {h['TargetHealth'].get('Reason', '')} {h['TargetHealth'].get('Description', '')}")
