# telepresence-demo

Minimal Flask "hello world" app for testing [Telepresence](https://www.telepresence.io/) intercepts on AKS.

- `GET /` — returns `<TITLE> (from pod: <hostname>)`, where `TITLE` is an env var (default `Hello World`)
- `GET /healthz` — returns `ok`

The `TITLE` env var exists so you can run a modified local copy and see the intercepted
response change without redeploying the cluster copy.

## 1. Build and push the image

Replace `REGISTRY` with your ACR login server (e.g. `myregistry.azurecr.io`).

```bash
az acr login --name REGISTRY
docker build -t REGISTRY/hello-world:latest .
docker push REGISTRY/hello-world:latest
```

If AKS is using a different ACR than the one you're logged into, attach it once:

```bash
az aks update -n <cluster-name> -g <resource-group> --attach-acr REGISTRY
```

## 2. Deploy to AKS

Update `image: REGISTRY/hello-world:latest` in [k8s/deployment.yaml](k8s/deployment.yaml) to match your registry, then:

```bash
az aks get-credentials -n <cluster-name> -g <resource-group>
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl -n telepresence-demo get pods,svc
```

Sanity check without Telepresence:

```bash
kubectl -n telepresence-demo port-forward svc/hello-world 8080:80
curl localhost:8080/
```

## 3. Run the app locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt
TITLE="Hello from my laptop" python app/main.py
curl localhost:8080/
```

## 4. Intercept with Telepresence

```bash
telepresence helm install          # first time only, installs traffic-manager
telepresence connect --namespace telepresence-demo

telepresence intercept hello-world --port 8080:80 --namespace telepresence-demo
```

With the intercept active, requests to the `hello-world` service in-cluster are routed to
your local process. Run the app locally (step 3) with a different `TITLE` and hit the
in-cluster service (or its public/ingress endpoint if you have one) — you should see your
local `TITLE` come back instead of the cluster deployment's.

Tear down:

```bash
telepresence leave hello-world
telepresence quit
```

## 5. GitHub Pages frontend

[docs/index.html](docs/index.html) is a static page that fetches the title text from the
API at `http://localhost:8080/` and displays it as the page heading/title. It only works
while the Flask app (step 3) or a `kubectl port-forward` / Telepresence intercept is
exposing the API on `localhost:8080` in the same browser session — GitHub Pages itself is
just static hosting, the page still calls your local machine.

Enable Pages for this repo once pushed to GitHub: **Settings → Pages → Source: Deploy from
branch → `main` / `docs`**. Then visit `https://<user>.github.io/telepresence-demo/` with
the API running locally to see the fetched title.

To point the page at a different API origin later (e.g. once you have a public AKS
ingress), edit the `API_URL` constant in [docs/index.html](docs/index.html).

## 6. Expose the API publicly on AKS (so GitHub Pages can reach it over HTTPS)

GitHub Pages is served over HTTPS, so browsers block a plain `http://` fetch to it as mixed
content. You need a real HTTPS endpoint for the API. The cleanest way is
`ingress-nginx` + `cert-manager` issuing a free Let's Encrypt certificate.

**Prerequisite: a domain/subdomain you control** (e.g. `hello.yourdomain.com`) that you can
point at the ingress's public IP. ⚠️ **Reminder: you said you'd provide this later** — the
manifests below use `hello.YOURDOMAIN.com` as a placeholder in
[k8s/ingress.yaml](k8s/ingress.yaml) and `YOUR_EMAIL@example.com` in
[k8s/cluster-issuer.yaml](k8s/cluster-issuer.yaml). Swap both before applying.

```bash
# 1. Install ingress-nginx
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace

# 2. Get the public IP assigned to the ingress LoadBalancer
kubectl -n ingress-nginx get svc ingress-nginx-controller

# 3. Point your DNS at that IP
#    Create an A record: hello.yourdomain.com -> <EXTERNAL-IP>

# 4. Install cert-manager
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set crds.enabled=true

# 5. Edit k8s/cluster-issuer.yaml and k8s/ingress.yaml with your real email/domain, then:
kubectl apply -f k8s/cluster-issuer.yaml
kubectl apply -f k8s/ingress.yaml

# 6. Wait for the certificate to be issued
kubectl -n telepresence-demo get certificate
kubectl -n telepresence-demo describe certificate hello-world-tls
```

Once the certificate shows `READY: True`, test it:

```bash
curl https://hello.yourdomain.com/
```

Then update `API_URL` in [docs/index.html](docs/index.html) to
`https://hello.yourdomain.com/` and commit/push — the GitHub Pages frontend will now hit
the real AKS-hosted API instead of `localhost`. You can also point the CORS header in
[app/main.py](app/main.py) at your GitHub Pages origin instead of `*` if you want to lock
it down (`https://<your-github-username>.github.io`).

**Telepresence still works the same way against the public endpoint** — traffic hitting
`https://hello.yourdomain.com/` goes through the ingress to the `hello-world` Service, and
an active intercept reroutes matching in-cluster traffic to your local process regardless
of whether the caller reached it via ingress, port-forward, or another in-cluster pod.
