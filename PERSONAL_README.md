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


## QA operativo — actualización 11/11/2026 (NO producción)
- PR correctivo en borrador: #2, rama `fix/personal-v1-safe-deletes-20261111`, basada en `feat/personal-v1-hardening`. No fusionar ni promover sin validar el entorno final.
- CI de esta rama: 29 pruebas PASS, incluidas seguridad de transacciones, sesión privada y recorrido de los siete módulos con servicios simulados.
- Neon QA: proyecto `my-first-project`, rama `qa-personal-v1-20261111`; las cinco tablas están presentes y hay un único registro ficticio bajo `qa-only@local.invalid`.
- Rama separada de ensayo de restauración: `qa-restore-verify-20261111`, con el mismo esquema, conteos, restricciones y huella de datos. La copia SQL QA debe almacenarse aparte. Esto NO acredita respaldo periódico ni recuperación de producción.
- Neon `production` continúa sin tablas públicas. No conectar la app a esa rama ni ejecutar `init_db()` allí sin la puerta de producción correspondiente.

### Instancia privada de Streamlit Community Cloud — secuencia de seguridad
1. Crear una **nueva app** apuntando al repo `flacogrosso/cultivo-la-carlota`, rama `fix/personal-v1-safe-deletes-20261111` y archivo `app.py`. **No configurar secretos todavía.** Como el repo es público, inicialmente puede abrirse una URL pública, pero el acceso de la app falla cerrado al faltar la contraseña.
2. Cambiar y verificar **Sharing → Only specific people can view this app**. Si la plataforma no permite privatizarla, detener la conexión; no introducir `DATABASE_URL` en una app pública.
3. Solo después de comprobar la privacidad, guardar los secretos en **Settings → Secrets** (nunca en Git ni chat):
   - `GLM_PERSONAL_ACCESS_PASSWORD`: contraseña única, fuerte, mínimo 16 caracteres.
   - `DATABASE_URL`: **únicamente** la cadena de la rama `qa-personal-v1-20261111`, copiada desde Neon para esa rama. Confirmar proyecto, rama y base `neondb` antes de guardarla.
   - `GLM_PERSONAL_ACCOUNT`: `qa-only@local.invalid` para leer el registro ficticio. **No usar un correo real en QA**.
4. Probar desde una sesión de incógnito: acceso sin autenticación, contraseña errónea, contraseña válida, módulo de seguimiento (registro QA visible), cierre de sesión y expiración. Verificar en Desktop y móvil, registrar errores y screenshots sin datos privados.
5. Deshabilitar la instancia QA o revocar credenciales de prueba cuando no se utilice. Nunca pasar la conexión QA a producción por accidente.

### Gate pendiente para uso personal definitivo
- Conexión de Streamlit QA real: NO VERIFICADA.
- Navegación con AppTest y redes/BD simuladas: PASS; pruebas con navegador y dispositivos reales: NO VERIFICADAS.
- Respaldo y restauración de QA ficticio: PASS; esquema/backup/productivo: NO VERIFICADO.
- Verificar protección en Streamlit Cloud, separar credenciales y contar con una copia recuperable de producción antes de crear el primer cultivo personal definitivo.
