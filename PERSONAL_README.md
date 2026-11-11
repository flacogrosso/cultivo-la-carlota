# GLM Cultivador — versión personal (rama de preparación)
Esta rama se prepara **solo para uso privado**. No tiene autorización para lanzarse comercialmente.

## Reglas de seguridad
- No trabajar directamente en `main`. No ejecutar migraciones destructivas ni borrar registros existentes.
- La aplicación exige `GLM_PERSONAL_ACCESS_PASSWORD` (secreto, mínimo 16 caracteres). Si falta, **no permite entrar**.
- `GLM_PERSONAL_ACCOUNT` es el identificador de los cultivos en la base existente: si ya hay datos históricos bajo otro correo, configurar **exactamente ese correo** para verlos. No copiarlos ni migrarlos a ciegas.
- `DATABASE_URL` debe apuntar a una base PostgreSQL existente y respaldada. No hay valores reales de credenciales en el repositorio.
- El modo personal omite el cobro, el alta de pruebas, los referidos y la promoción comercial. El código se conserva en la rama para una evaluación futura.
- No publicar una URL abierta: proteger el acceso a la instancia, además de la contraseña en la aplicación.
- Nunca poner credenciales en Git, capturas, logs o mensajes.

## Encendido previsto
1. Crear un respaldo verificable de PostgreSQL, fuera del repositorio.
2. Configurar los tres secretos de entorno en Replit: `GLM_PERSONAL_ACCESS_PASSWORD`, `DATABASE_URL`, `GLM_PERSONAL_ACCOUNT`.
3. Iniciar vista previa de Replit con el comando correspondiente al proyecto (sin publicar deployment).
4. Ingresar con la contraseña configurada y comprobar los siete módulos, ubicación, persistencia y cierre de sesión.
5. Desconectar/reconectar y verificar que el historial permanezca. Probar acceso no autenticado en una ventana de incógnito.

## Gates antes de ponerlo en uso
- [ ] Respaldo de base y registro de origen/propietario confirmados
- [ ] Código personal probado con tests
- [ ] Instancia arranca con variables configuradas
- [ ] Sin secretos en Git ni URL de acceso público sin protección
- [ ] Autenticación privada, logout y expiración de sesión
- [ ] Guardado y recuperación en PostgreSQL verificados (sin borrar datos preexistentes)
- [ ] Módulos y diseño móvil verificados con datos de prueba
- [ ] Verificada la configuración efectiva de XSRF, dominio y cookies

**Este README no es evidencia de QA ni de despliegue.**
