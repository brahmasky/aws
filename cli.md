aws ec2 delete-tags --resources `id1` `id2` --tags Key=MaintenanceWindow

aws secretsmanager create-secret --region `REGION` --name `NAME` --secret-string '{"key1":"value1","key2":"value2"}'

aws --region `REGION` secretsmanager update-secret --secret-id `NAME` --secret-string '{"key1":"value1","key2":"value2"}'

aws secretsmanager get-secret-value --secret-id `NAME` --region `REGION`

aws secretsmanager list-secrets |jq '.[] | .[] |.Name'

aws secretsmanager get-secret-value --secret-id `NAME` |jq '.SecretString'

aws autoscaling describe-auto-scaling-instances |jq '.[] | .[] |(select(.AutoScalingGroupName|contains("`KEYWOR`"))) |.InstanceId, .AutoScalingGroupName'


aws autoscaling describe-auto-scaling-groups --query 'AutoScalingGroups[?contains(AutoScalingGroupName, `<<KEYWORD>>`) == `true`].Instances[]'

### list and terminate instances
>aws ec2 describe-instances --filters "Name=tag:Name,Values=<<NAME_TAG>>" --query "Reservations[].Instances[].InstanceId"

>aws ec2 describe-instances --filters "Name=tag:Name,Values=<<NAME_TAG>> Name=instance-state-name,Values=running" --query "Reservations[].Instances[].InstanceId"

>aws ec2 terminate-instances --instance-ids <<INSTANCE_ID>>

### desscribe volumes
>aws ec2 describe-instances  --filters Name=block-device-mapping.device-name,Values=/dev/xvdg --query 'Reservations[*].Instances[*].[Tags[?Key==`Name`].Value,InstanceId,BlockDeviceMappings[*].DeviceName,BlockDeviceMappings[*].Ebs.VolumeId]' --output text

>aws ec2 describe-volumes --filters "Name=attachment.device,Values=/dev/xvdg" --query "Volumes[*].Attachments[*].{Name:Device,ID:VolumeId}" --output table

### multiple tags
aws ec2 describe-instances --filters "Name=tag:Role,Values=123" "Name=tag:aws:ID,Values=abc" --query "Reservations[*].Instances[*].InstanceId" --output text
