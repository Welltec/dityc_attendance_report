# -*- coding: utf-8 -*-

from odoo import models, fields, api, tools, _
from odoo.fields import Datetime
from datetime import datetime, timedelta
import pytz
import json
from lxml import etree
import base64
import xlsxwriter
from io import BytesIO
import logging
from dateutil.relativedelta import relativedelta
from psycopg2.extensions import AsIs
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AttendanceRealtimeView(models.Model):
    _name = 'dityc.attendance.realtime.view'
    _description = 'Vista en Tiempo Real de Asistencias'
    _auto = False
    _order = 'fecha desc, employee_id, entrada'

    id = fields.Integer(string='ID', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Empleado', readonly=True)
    company_id = fields.Many2one('res.company', string='Compañía', readonly=True)
    fecha = fields.Date(string='Fecha', readonly=True)
    dia_semana = fields.Char(string='Día', readonly=True)
    entrada = fields.Datetime(string='Entrada', readonly=True)
    salida = fields.Datetime(string='Salida', readonly=True)
    tipo_dia = fields.Selection([
        ('habil', 'Hábil'),
        ('sabado_am', 'Sáb AM'),
        ('sabado_pm', 'Sáb PM'),
        ('domingo', 'Dom'),
        ('feriado', 'Feriado'),
        ('no_laborable', 'No Lab.')
    ], string='Tipo', readonly=True)
    es_feriado = fields.Boolean(string='Feriado', readonly=True)
    nombre_feriado = fields.Char(string='Desc. Feriado', readonly=True)
    horas_semana_normal = fields.Float(string='Normal L-V', digits=(16, 2), readonly=True)
    horas_sabado_50 = fields.Float(string='50% Sáb', digits=(16, 2), readonly=True)
    horas_extra_100 = fields.Float(string='100% S/D', digits=(16, 2), readonly=True)
    horas_feriado = fields.Float(string='Hrs Feriado', digits=(16, 2), readonly=True)
    total_horas_trabajadas = fields.Float(string='Total Hrs', digits=(16, 2), readonly=True)

    @api.model
    def init(self):
        """Inicializa la vista materializada"""
        try:
            # Para una vista normal, simplemente la reemplazamos
            tools.drop_view_if_exists(self.env.cr, self._table)
            _logger.info("Vista %s eliminada, se creará desde cero", self._table)
              
            # Establecer la zona horaria para toda la sesión
            self.env.cr.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            
            # Crear la vista
            self.env.cr.execute("""
                -- Crear vista con zona horaria America/Argentina/Buenos_Aires
                CREATE OR REPLACE VIEW dityc_attendance_realtime_view AS
                WITH 
                -- Constantes y configuración
                config AS (
                    SELECT 
                        'America/Argentina/Buenos_Aires'::text as zona_horaria,
                        '00:01:00'::time as inicio_dia,
                        '13:00:00'::time as corte_sabado,
                        '23:59:59'::time as fin_dia,
                        3::integer as meses_historia,
                        -- Límites de horas por tipo
                        24.0::float as max_horas_dia,
                        13.0::float as max_horas_sabado_am,
                        11.0::float as max_horas_sabado_pm
                ),
                -- Fechas de inicio y fin del período
                periodo AS (
                    SELECT 
                        date_trunc('month', timezone(
                            (SELECT zona_horaria FROM config), 
                            CURRENT_TIMESTAMP
                        ) - interval '2 month')::date as fecha_inicio,
                        date_trunc('month', timezone(
                            (SELECT zona_horaria FROM config), 
                            CURRENT_TIMESTAMP + interval '1 month'
                        ) - interval '1 day')::date as fecha_fin
                ),
                -- Normalizar registros de asistencia a zona horaria local
                asistencias_local AS (
                    SELECT 
                        a.id,
                        a.employee_id,
                        e.company_id,
                        -- Convertir fechas/horas a zona horaria local
                        timezone(
                            (SELECT zona_horaria FROM config),
                            a.check_in AT TIME ZONE 'UTC'
                        ) as entrada_local,
                        timezone(
                            (SELECT zona_horaria FROM config),
                            a.check_out AT TIME ZONE 'UTC'
                        ) as salida_local,
                        -- Extraer componentes de fecha/hora
                        timezone(
                            (SELECT zona_horaria FROM config),
                            a.check_in AT TIME ZONE 'UTC'
                        )::date as fecha,
                        timezone(
                            (SELECT zona_horaria FROM config),
                            a.check_in AT TIME ZONE 'UTC'
                        )::time as hora_entrada,
                        timezone(
                            (SELECT zona_horaria FROM config),
                            a.check_out AT TIME ZONE 'UTC'
                        )::time as hora_salida,
                        -- Calcular horas totales
                        ROUND(
                            EXTRACT(EPOCH FROM (
                                timezone(
                                    (SELECT zona_horaria FROM config),
                                    a.check_out AT TIME ZONE 'UTC'
                                ) - 
                                timezone(
                                    (SELECT zona_horaria FROM config),
                                    a.check_in AT TIME ZONE 'UTC'
                                )
                            )) / 3600.0,
                            2
                        ) as horas_totales
                    FROM hr_attendance a
                    JOIN hr_employee e ON e.id = a.employee_id
                    WHERE 
                        a.check_in IS NOT NULL 
                        AND a.check_out IS NOT NULL
                        AND a.check_out > a.check_in
                        AND timezone(
                            (SELECT zona_horaria FROM config),
                            a.check_in AT TIME ZONE 'UTC'
                        )::date >= (SELECT fecha_inicio FROM periodo)
                ),
                -- Obtener feriados
                feriados AS (
                    SELECT 
                        l.employee_id,
                        l.request_date_from::date as fecha,
                        lt.name::text as nombre_feriado
                    FROM hr_leave l
                    JOIN hr_leave_type lt ON l.holiday_status_id = lt.id
                    WHERE 
                        lt.work_entry_type_id IN (
                            SELECT id FROM hr_work_entry_type WHERE is_leave IS TRUE
                        )
                        AND l.state = 'validate'
                        AND l.request_date_from::date >= (SELECT fecha_inicio FROM periodo)
                    
                    UNION
                    
                    -- Feriados nacionales para todos los empleados
                    SELECT 
                        e.id as employee_id,
                        national_holidays.date_holiday as fecha,
                        national_holidays.name::text as nombre_feriado
                    FROM hr_employee e
                    CROSS JOIN (
                        -- Lista de feriados nacionales que aplican a todos los empleados
                        SELECT '2025-04-02'::date as date_holiday, 'Día de los Veteranos y Caídos en Malvinas'::text as name
                        UNION ALL SELECT '2025-01-01'::date, 'Año Nuevo'::text
                        UNION ALL SELECT '2025-02-24'::date, 'Carnaval'::text
                        UNION ALL SELECT '2025-02-25'::date, 'Carnaval'::text
                        UNION ALL SELECT '2025-03-24'::date, 'Día de la Memoria'::text
                        UNION ALL SELECT '2025-04-18'::date, 'Viernes Santo'::text
                        UNION ALL SELECT '2025-05-01'::date, 'Día del Trabajador'::text
                        UNION ALL SELECT '2025-05-25'::date, 'Día de la Revolución de Mayo'::text
                        UNION ALL SELECT '2025-06-20'::date, 'Día de la Bandera'::text
                        UNION ALL SELECT '2025-07-09'::date, 'Día de la Independencia'::text
                        UNION ALL SELECT '2025-08-17'::date, 'Paso a la Inmortalidad del Gral. San Martín'::text
                        UNION ALL SELECT '2025-10-12'::date, 'Día del Respeto a la Diversidad Cultural'::text
                        UNION ALL SELECT '2025-11-20'::date, 'Día de la Soberanía Nacional'::text
                        UNION ALL SELECT '2025-12-08'::date, 'Inmaculada Concepción de María'::text
                        UNION ALL SELECT '2025-12-25'::date, 'Navidad'::text
                    ) AS national_holidays
                    WHERE date_holiday >= (SELECT fecha_inicio FROM periodo)
                ),
                -- Calcular horas por regla
                horas_calculadas AS (
                    SELECT 
                        a.*,
                        -- Horas feriado (evaluamos primero)
                        CASE 
                            WHEN EXISTS (
                                SELECT 1 FROM feriados f 
                                WHERE f.employee_id = a.employee_id 
                                AND f.fecha = a.fecha
                            ) THEN a.horas_totales
                            ELSE 0
                        END as horas_feriado,
                        -- Horas normales (L-V) solo si no es feriado
                        CASE 
                            WHEN EXTRACT(DOW FROM a.fecha) BETWEEN 1 AND 5
                            AND NOT EXISTS (
                                SELECT 1 FROM feriados f 
                                WHERE f.employee_id = a.employee_id 
                                AND f.fecha = a.fecha
                            )
                            THEN LEAST(a.horas_totales, (SELECT max_horas_dia FROM config))
                            ELSE 0
                        END as horas_normales,
                        -- Horas sábado 50% (hasta 13:00) solo si no es feriado
                        CASE 
                            WHEN EXTRACT(DOW FROM a.fecha) = 6
                            AND NOT EXISTS (
                                SELECT 1 FROM feriados f 
                                WHERE f.employee_id = a.employee_id 
                                AND f.fecha = a.fecha
                            )
                            THEN 
                                CASE
                                    -- Todo el período antes de las 13:00
                                    WHEN a.hora_salida <= (SELECT corte_sabado FROM config)
                                    THEN LEAST(a.horas_totales, (SELECT max_horas_sabado_am FROM config))
                                    -- Período que cruza las 13:00
                                    WHEN a.hora_entrada < (SELECT corte_sabado FROM config)
                                    THEN LEAST(
                                        EXTRACT(EPOCH FROM (
                                            (a.fecha + (SELECT corte_sabado FROM config))::timestamp - 
                                            a.entrada_local
                                        )) / 3600.0,
                                        (SELECT max_horas_sabado_am FROM config)
                                    )
                                    ELSE 0
                                END
                            ELSE 0
                        END as horas_sabado_50,
                        -- Horas 100% (sábado después de 13:00 y domingo) solo si no es feriado
                        CASE 
                            WHEN EXTRACT(DOW FROM a.fecha) IN (0, 6)  -- Domingo o Sábado
                            AND NOT EXISTS (
                                SELECT 1 FROM feriados f 
                                WHERE f.employee_id = a.employee_id 
                                AND f.fecha = a.fecha
                            )
                            THEN 
                                CASE
                                    WHEN EXTRACT(DOW FROM a.fecha) = 0  -- Domingo
                                    THEN LEAST(a.horas_totales, (SELECT max_horas_dia FROM config))
                                    WHEN EXTRACT(DOW FROM a.fecha) = 6  -- Sábado
                                    THEN 
                                        CASE
                                            -- Todo el período después de las 13:00
                                            WHEN a.hora_entrada >= (SELECT corte_sabado FROM config)
                                            THEN LEAST(a.horas_totales, (SELECT max_horas_sabado_pm FROM config))
                                            -- Período que cruza las 13:00
                                            WHEN a.hora_entrada < (SELECT corte_sabado FROM config)
                                            AND a.hora_salida > (SELECT corte_sabado FROM config)
                                            THEN LEAST(
                                                EXTRACT(EPOCH FROM (
                                                    a.salida_local - 
                                                    (a.fecha + (SELECT corte_sabado FROM config))::timestamp
                                                )) / 3600.0,
                                                (SELECT max_horas_sabado_pm FROM config)
                                            )
                                            ELSE 0
                                        END
                                    ELSE 0
                                END
                            ELSE 0
                        END as horas_extra_100
                    FROM asistencias_local a
                ),
                -- Generar serie de fechas y empleados
                fechas_empleados AS (
                    SELECT 
                        e.id as employee_id,
                        e.company_id,
                        d::date as fecha,
                        EXTRACT(DOW FROM d::date) as dia_semana,
                        CASE EXTRACT(DOW FROM d::date)
                            WHEN 0 THEN 'Domingo'
                            WHEN 1 THEN 'Lunes'
                            WHEN 2 THEN 'Martes'
                            WHEN 3 THEN 'Miércoles'
                            WHEN 4 THEN 'Jueves'
                            WHEN 5 THEN 'Viernes'
                            WHEN 6 THEN 'Sábado'
                        END as nombre_dia
                    FROM hr_employee e
                    CROSS JOIN generate_series(
                        (SELECT fecha_inicio FROM periodo),
                        (SELECT fecha_fin FROM periodo),
                        '1 day'::interval
                    ) d
                    WHERE e.active = true
                )
                -- Consulta final
                SELECT 
                    COALESCE(h.id, -fe.employee_id) as id,
                    fe.employee_id,
                    fe.company_id,
                    fe.fecha,
                    fe.nombre_dia as dia_semana,
                    -- Convertir a UTC para almacenamiento
                    h.entrada_local AT TIME ZONE (SELECT zona_horaria FROM config) AT TIME ZONE 'UTC' as entrada,
                    h.salida_local AT TIME ZONE (SELECT zona_horaria FROM config) AT TIME ZONE 'UTC' as salida,
                    -- Determinar tipo de día
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM feriados f 
                            WHERE f.employee_id = fe.employee_id 
                            AND f.fecha = fe.fecha
                        ) THEN 'feriado'
                        WHEN fe.dia_semana = 0 THEN 'domingo'
                        WHEN fe.dia_semana = 6 THEN 
                            CASE 
                                WHEN h.hora_salida <= (SELECT corte_sabado FROM config) THEN 'sabado_am'
                                ELSE 'sabado_pm'
                            END
                        ELSE 'habil'
                    END as tipo_dia,
                    -- Indicador de feriado
                    EXISTS (
                        SELECT 1 FROM feriados f 
                        WHERE f.employee_id = fe.employee_id 
                        AND f.fecha = fe.fecha
                    ) as es_feriado,
                    -- Nombre del feriado
                    (
                        SELECT f.nombre_feriado 
                        FROM feriados f 
                        WHERE f.employee_id = fe.employee_id 
                        AND f.fecha = fe.fecha 
                        LIMIT 1
                    ) as nombre_feriado,
                    -- Horas calculadas con casting explícito
                    ROUND(COALESCE(h.horas_normales, 0)::numeric, 2) as horas_semana_normal,
                    ROUND(COALESCE(h.horas_sabado_50, 0)::numeric, 2) as horas_sabado_50,
                    ROUND(COALESCE(h.horas_extra_100, 0)::numeric, 2) as horas_extra_100,
                    -- Horas feriado
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 FROM feriados f 
                            WHERE f.employee_id = fe.employee_id 
                            AND f.fecha = fe.fecha
                        ) THEN ROUND(COALESCE(h.horas_feriado, 0)::numeric, 2)
                        ELSE 0
                    END as horas_feriado,
                    -- Total de horas
                    ROUND(COALESCE(h.horas_totales, 0)::numeric, 2) as total_horas_trabajadas
                FROM fechas_empleados fe
                LEFT JOIN horas_calculadas h ON 
                    fe.employee_id = h.employee_id 
                    AND fe.fecha = h.fecha
                ORDER BY fe.fecha DESC, fe.employee_id;
            """)
            _logger.info("Vista %s creada exitosamente", self._table)
            
            # Asegurarse de que el caché se actualiza
            self._notificar_cambios_cache()
            
        except Exception as e:
            _logger.error("Error al inicializar la vista materializada: %s", str(e))
            raise

    @api.model
    def _notificar_cambios_cache(self):
        """Notifica al caché que la vista se ha actualizado"""
        try:
            # Llamar al método de actualización automática del caché
            result = self.env['dityc.attendance.realtime.cache']._actualizar_cache_automatico()
            if result:
                _logger.info("Notificación de cambios enviada al caché y procesada correctamente")
            else:
                _logger.warning("No se pudo actualizar el caché, posiblemente porque la vista aún no está lista")
        except Exception as e:
            _logger.error(f"Error al notificar cambios al caché: {str(e)}")
            # No propagar el error para evitar que falle la inicialización de la vista

    @api.model
    def _actualizar_vista(self):
        """Actualiza la vista materializada"""
        try:
            _logger.info("Actualizando vista materializada")
            self.init()
            _logger.info("Vista materializada actualizada exitosamente")
        except Exception as e:
            _logger.error("Error al actualizar la vista materializada: %s", str(e))
            raise

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """Sobrescribe fields_view_get para agregar campos dinámicos a la vista"""
        result = super(AttendanceRealtimeView, self).fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
        
        if view_type == 'tree':
            try:
                # Obtener el elemento tree
                doc = etree.XML(result['arch'])
                nodes = doc.xpath("//tree")
                if not nodes:
                    return result
                    
                tree = nodes[0]
                
                # Agregar total_horas_trabajadas al final
                total_horas = etree.Element('field', {
                    'name': 'total_horas_trabajadas',
                    'widget': 'float_time',
                    'sum': 'Total'
                })
                tree.append(total_horas)
                
                result['arch'] = etree.tostring(doc, encoding='unicode')
                _logger.info(f"Vista modificada exitosamente: {result['arch']}")
            except Exception as e:
                _logger.error(f"Error modificando la vista: {str(e)}")
        
        return result

    def export_xlsx(self):
        """Exporta los datos a Excel"""
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/export/xlsx_attendance_report',
            'target': 'self',
        }

    def refresh_view(self):
        """Actualiza la vista desde la interfaz de usuario"""
        try:
            self.env.cr.execute("SET TIME ZONE 'America/Argentina/Buenos_Aires'")
            self.init()
            # Actualizar los datos en el caché
            self._notificar_cambios_cache()
            # Para refrescar la vista en la interfaz
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        except Exception as e:
            _logger.error("Error al actualizar la vista: %s", str(e))
            raise UserError(_("Error al actualizar la vista: %s") % str(e))

    def clear_attendance_data(self):
        """Vacía la tabla de datos de asistencia"""
        try:
            _logger.info("Iniciando limpieza de datos de asistencia")
            # Eliminar la vista
            self.env.cr.execute("DROP VIEW IF EXISTS %s", (AsIs(self._table),))
            # Recrear la vista vacía
            self.init()
            # Notificar al caché
            self._notificar_cambios_cache()
            # Mostrar mensaje de éxito
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('Los datos han sido vaciados correctamente.'),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    },
                }
            }
        except Exception as e:
            _logger.error("Error al vaciar los datos: %s", str(e))
            raise UserError(_("Error al vaciar los datos: %s") % str(e)) 