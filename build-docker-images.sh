# Build and tag the main application image
docker build -t registry.rijsinghani.us/neuralami:staging .
# Build and tag the worker image
docker build -t registry.rijsinghani.us/neuralami-worker:staging -f worker/Dockerfile .