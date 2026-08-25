import { createApp } from "vue"
import App from "./App.vue"
import router from "./router"
import "./styles.css"
import "./styles/admin-theme.css"

const app = createApp(App)

app.use(router).mount("#app")
