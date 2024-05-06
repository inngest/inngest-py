from src.inngest import inngest_client

import inngest.digital_ocean
from examples import functions
from inngest.experimental.digital_ocean_simulator import DigitalOceanSimulator

main = inngest.digital_ocean.serve(
    inngest_client,
    functions.create_sync_functions(inngest_client),
)

# This should not be used in production. It's just for locally running
# Inngestful DigitalOcean Functions
DigitalOceanSimulator(main).app.run(port=8000)
