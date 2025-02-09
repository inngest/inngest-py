import inngest.digital_ocean
from inngest.experimental.digital_ocean_simulator import DigitalOceanSimulator
from src.inngest.client import inngest_client
from src.inngest.functions import hello

main = inngest.digital_ocean.serve(
    inngest_client,
    [hello],
)

# This should not be used in production. It's just for locally running
# Inngestful DigitalOcean Functions
DigitalOceanSimulator(main).app.run(port=8000)
