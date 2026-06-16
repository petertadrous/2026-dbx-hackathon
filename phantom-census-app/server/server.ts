import { createApp, lakebase, server } from '@databricks/appkit';
import { setupPhantomCensusRoutes } from './routes/phantom-census-routes';

createApp({
  plugins: [
    lakebase(),
    server(),
  ],
  async onPluginsReady(appkit) {
    await setupPhantomCensusRoutes(appkit);
  },
}).catch(console.error);
