from odoo import models
from datetime import datetime


class AttendanceReportXlsx(models.AbstractModel):
    _name = 'report.dityc_attendance_report.attendance_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Reporte de Asistencias en Excel'

    def _get_header_style(self, workbook):
        """Estilo para encabezados"""
        header_style = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'fg_color': '#D3D3D3',
            'border': 1
        })
        return header_style

    def _get_cell_style(self, workbook, tipo='normal'):
        """Estilos para celdas según el tipo"""
        styles = {
            'normal': {'border': 1},
            'feriado': {'border': 1, 'bg_color': '#FFE4B5'},  # Beige claro
            'sabado': {'border': 1, 'bg_color': '#E0FFFF'},   # Celeste claro
            'total': {'border': 1, 'bold': True, 'bg_color': '#F0F0F0'}
        }
        return workbook.add_format(styles.get(tipo, styles['normal']))

    def _prepare_report_data(self, records):
        """Prepara los datos para el reporte"""
        # Calcular totales
        totales = {
            'normal': sum(records.mapped('horas_semana_normal')),
            'sabado_50': sum(records.mapped('horas_sabado_50')),
            'extra_100': sum(records.mapped('horas_extra_100')),
            'feriado': sum(records.mapped('horas_feriado')),
            'total': sum(records.mapped('total_horas_trabajadas'))
        }

        # Si hay registros agrupados por empleado
        if len(records.mapped('employee_id')) > 1:
            grupos = []
            for employee in records.mapped('employee_id'):
                registros_empleado = records.filtered(lambda r: r.employee_id == employee)
                grupos.append({
                    'empleado': employee,
                    'registros': registros_empleado,
                    'totales': {
                        'normal': sum(registros_empleado.mapped('horas_semana_normal')),
                        'sabado_50': sum(registros_empleado.mapped('horas_sabado_50')),
                        'extra_100': sum(registros_empleado.mapped('horas_extra_100')),
                        'feriado': sum(registros_empleado.mapped('horas_feriado')),
                        'total': sum(registros_empleado.mapped('total_horas_trabajadas'))
                    }
                })
            return {
                'tipo': 'agrupado',
                'grupos': grupos,
                'totales_generales': totales
            }
        else:
            return {
                'tipo': 'individual',
                'empleado': records[0].employee_id if records else False,
                'registros': records,
                'totales': totales
            }

    def generate_xlsx_report(self, workbook, data, records):
        """Genera el reporte Excel"""
        # Preparar datos
        report_data = self._prepare_report_data(records)
        tipo = report_data['tipo']

        # Crear hoja
        sheet = workbook.add_worksheet('Asistencias')
        sheet.set_column('A:A', 20)  # Empleado
        sheet.set_column('B:B', 12)  # Fecha
        sheet.set_column('C:C', 12)  # Día
        sheet.set_column('D:E', 18)  # Entrada/Salida
        sheet.set_column('F:J', 12)  # Horas

        # Escribir encabezado general
        header_style = self._get_header_style(workbook)
        sheet.merge_range('A1:J1', 'Reporte de Asistencias', header_style)
        
        row = 2
        if tipo == 'individual':
            # Encabezados
            headers = ['Fecha', 'Día', 'Entrada', 'Salida', 'Normal', '50%', '100%', 'Feriado', 'Total']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_style)
            row += 1

            # Datos
            for reg in report_data['registros']:
                style = self._get_cell_style(workbook, 
                    'feriado' if reg.es_feriado else 
                    'sabado' if reg.tipo_dia in ['sabado_am', 'sabado_pm'] else 'normal')
                
                sheet.write(row, 0, reg.fecha.strftime('%Y-%m-%d'), style)
                sheet.write(row, 1, reg.dia_semana, style)
                sheet.write(row, 2, reg.entrada.strftime('%H:%M:%S') if reg.entrada else '', style)
                sheet.write(row, 3, reg.salida.strftime('%H:%M:%S') if reg.salida else '', style)
                sheet.write(row, 4, reg.horas_semana_normal, style)
                sheet.write(row, 5, reg.horas_sabado_50, style)
                sheet.write(row, 6, reg.horas_extra_100, style)
                sheet.write(row, 7, reg.horas_feriado, style)
                sheet.write(row, 8, reg.total_horas_trabajadas, style)
                row += 1

            # Totales
            total_style = self._get_cell_style(workbook, 'total')
            sheet.merge_range(row, 0, row, 3, 'Totales', total_style)
            sheet.write(row, 4, report_data['totales']['normal'], total_style)
            sheet.write(row, 5, report_data['totales']['sabado_50'], total_style)
            sheet.write(row, 6, report_data['totales']['extra_100'], total_style)
            sheet.write(row, 7, report_data['totales']['feriado'], total_style)
            sheet.write(row, 8, report_data['totales']['total'], total_style)

        else:  # tipo == 'agrupado'
            for grupo in report_data['grupos']:
                # Encabezado del empleado
                sheet.merge_range(row, 0, row, 8, grupo['empleado'].name, header_style)
                row += 1

                # Encabezados de columnas
                headers = ['Fecha', 'Día', 'Entrada', 'Salida', 'Normal', '50%', '100%', 'Feriado', 'Total']
                for col, header in enumerate(headers):
                    sheet.write(row, col, header, header_style)
                row += 1

                # Datos del empleado
                for reg in grupo['registros']:
                    style = self._get_cell_style(workbook,
                        'feriado' if reg.es_feriado else
                        'sabado' if reg.tipo_dia in ['sabado_am', 'sabado_pm'] else 'normal')
                    
                    sheet.write(row, 0, reg.fecha.strftime('%Y-%m-%d'), style)
                    sheet.write(row, 1, reg.dia_semana, style)
                    sheet.write(row, 2, reg.entrada.strftime('%H:%M:%S') if reg.entrada else '', style)
                    sheet.write(row, 3, reg.salida.strftime('%H:%M:%S') if reg.salida else '', style)
                    sheet.write(row, 4, reg.horas_semana_normal, style)
                    sheet.write(row, 5, reg.horas_sabado_50, style)
                    sheet.write(row, 6, reg.horas_extra_100, style)
                    sheet.write(row, 7, reg.horas_feriado, style)
                    sheet.write(row, 8, reg.total_horas_trabajadas, style)
                    row += 1

                # Subtotales del empleado
                total_style = self._get_cell_style(workbook, 'total')
                sheet.merge_range(row, 0, row, 3, 'Subtotales', total_style)
                sheet.write(row, 4, grupo['totales']['normal'], total_style)
                sheet.write(row, 5, grupo['totales']['sabado_50'], total_style)
                sheet.write(row, 6, grupo['totales']['extra_100'], total_style)
                sheet.write(row, 7, grupo['totales']['feriado'], total_style)
                sheet.write(row, 8, grupo['totales']['total'], total_style)
                row += 2

            # Totales generales
            sheet.merge_range(row, 0, row, 8, 'Totales Generales', header_style)
            row += 1
            total_style = self._get_cell_style(workbook, 'total')
            sheet.merge_range(row, 0, row, 3, 'Total', total_style)
            sheet.write(row, 4, report_data['totales_generales']['normal'], total_style)
            sheet.write(row, 5, report_data['totales_generales']['sabado_50'], total_style)
            sheet.write(row, 6, report_data['totales_generales']['extra_100'], total_style)
            sheet.write(row, 7, report_data['totales_generales']['feriado'], total_style)
            sheet.write(row, 8, report_data['totales_generales']['total'], total_style) 