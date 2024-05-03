from src.inngest import inngest_client

import inngest.digital_ocean
import inngest.experimental
from examples import functions

main = inngest.digital_ocean.serve(
    inngest_client,
    functions.create_sync_functions(inngest_client),
)

# This should not be used in production. It's just for locally running
# Inngestful DigitalOcean Functions
inngest.experimental.DigitalOceanSimulator(main).app.run(port=8000)
