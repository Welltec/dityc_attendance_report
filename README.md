# Módulo de Reporte de Asistencias para Odoo 17

Este módulo extiende la funcionalidad de asistencias de Odoo, proporcionando un sistema avanzado de reportes con cálculo automático de horas trabajadas según distintas categorías y reglas de negocio.

## Características

- Vista de asistencias en tiempo real con cálculo automático de horas trabajadas
- Clasificación de horas trabajadas en diferentes categorías:
  - Horas normales (lunes a viernes)
  - Horas con recargo del 50% (sábados AM)
  - Horas con recargo del 100% (sábados PM, domingos y feriados)
  - Horas en días feriados
- Exportación a formato XLSX
- Reportes en PDF
- Interfaz amigable y filtros avanzados
- Sistema de caché para optimizar el rendimiento

## Reglas de Cálculo de Horas

Este módulo implementa las siguientes reglas para el cálculo de horas:

### 1. Horas Normales
- Se contabilizan solo en días hábiles (lunes a viernes)
- No se aplican en feriados, sábados ni domingos

### 2. Horas con Recargo del 50%
- **Sábados con salida antes o igual a las 13:00**: Todas las horas trabajadas
- **Sábados con entrada antes de 13:00 y salida después de 13:00**: Solo las horas trabajadas hasta las 13:00

### 3. Horas con Recargo del 100%
- **Domingos**: Todas las horas trabajadas
- **Sábados con entrada a partir de las 13:00**: Todas las horas trabajadas
- **Sábados con entrada antes de 13:00 y salida después de 13:00**: Solo las horas trabajadas después de las 13:00

### 4. Horas en Días Feriados
- Todas las horas trabajadas en días configurados como feriados

## Instalación

1. Clonar este repositorio en la carpeta de addons de Odoo
2. Actualizar la lista de módulos
3. Instalar el módulo "DITYC Attendance Report"

## Configuración

Para configurar correctamente el módulo:

1. Verificar que los empleados tengan correctamente asignados sus horarios de trabajo
2. Configurar los días feriados en el módulo de Ausencias/Tiempo Libre
3. Asegurarse de que la zona horaria del servidor esté correctamente configurada

## Uso

Una vez instalado, se agregará un nuevo menú "Reportes de Asistencia" bajo el menú principal de Asistencias.

## Créditos

Desarrollado por DITYC para Odoo 17.

## Licencia

Este módulo está licenciado bajo LGPL-3. 