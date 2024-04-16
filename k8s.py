from kubernetes import client, config
import time
from uuid import uuid4

def create_deployment_object(requestor, nick, nats_host, etcd_endpoints, deployment_name):
    # Configureate Pod template container
    image_pull_secret = [client.V1LocalObjectReference(name="regcred")]
    container = client.V1Container(
        name="worker",    
        image="ghcr.io/dgghq/hackwrld-client:main",
        image_pull_policy="Always",
        env=[client.V1EnvVar(name="ID", value=requestor),
             client.V1EnvVar(name="NICK", value=nick),
             client.V1EnvVar(name="NATS_HOST", value=nats_host),
             client.V1EnvVar(name="PORT", value="80"),
             client.V1EnvVar(name="ETCD_ENDPOINTS", value=etcd_endpoints),
             client.V1EnvVar(name="GIN_MODE", value="release")],
        ports=[client.V1ContainerPort(container_port=80)],
        resources=client.V1ResourceRequirements(
            limits={"memory": "50Mi"},
        ),
    )

    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={
                "id": requestor,
                "app": deployment_name,
                "hackwrld": "player",
                "creationDate": str(int(time.time()))
            },
        ),
        spec=client.V1PodSpec(containers=[container], image_pull_secrets=image_pull_secret),
    )

    # Create the specification of deployment
    spec = client.V1DeploymentSpec(
        replicas=1, template=template, selector={
            "matchLabels":
            {"app": deployment_name}})

    # Instantiate the deployment object
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=f"{requestor}-commandcenter", labels={
            "id": requestor,
            "nick": nick,
            "app": deployment_name,
            "hackwrld-component": "client"
        }),
        spec=spec,
    )
    return deployment


def get_cc_ip(userId, namespace) -> list:
    config.load_config()
    v1 = client.CoreV1Api()
    mypods = v1.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"id={userId}", 
        watch=False
    )
    ccs = []
    for pod in mypods.items:
        ccs.append({
            "ip": pod.status.pod_ip
        })
    return ccs