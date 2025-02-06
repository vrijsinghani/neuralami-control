import { FC, useMemo } from 'react';

// @mui material components
import { Table as MuiTable, TableBody, TableContainer, TableRow, TableCell } from '@mui/material';

// Custom components
import SoftBox from '../../SoftBox';
import SoftTypography from '../../SoftTypography';

interface Column {
  name: string;
  align?: 'left' | 'right' | 'center';
  width?: string | number;
}

interface TableProps {
  columns: Column[];
  rows: {
    [key: string]: any;
  }[];
  isSorted?: boolean;
  noEndBorder?: boolean;
}

const Table: FC<TableProps> = ({ columns, rows, isSorted = false, noEndBorder = false }) => {
  const renderColumns = columns.map(({ name, align = "left", width }, key) => {
    return (
      <SoftBox
        key={name}
        component="th"
        width={width || "auto"}
        pt={1.5}
        pb={1.25}
        pl={align === "left" ? 3 : 1}
        pr={align === "right" ? 3 : 1}
        textAlign={align}
        fontSize="12px"
        fontWeight="medium"
        color="secondary"
        opacity={0.7}
        borderBottom="1px solid"
        borderColor="grey.200"
      >
        <SoftTypography
          variant="caption"
          color="text"
          fontWeight="medium"
          textTransform="capitalize"
        >
          {name}
        </SoftTypography>
      </SoftBox>
    );
  });

  const renderRows = rows.map((row, key) => {
    const rowKey = `row-${key}`;
    const tableRow = columns.map(({ name, align = "left" }) => {
      return (
        <TableCell
          key={name}
          align={align}
          padding="none"
          sx={{
            border: 'none',
            pl: align === "left" ? 3 : 1,
            pr: align === "right" ? 3 : 1,
            pt: 1,
            pb: 1,
          }}
        >
          <SoftBox
            display="inline-block"
            width="100%"
            color="text"
            sx={{ verticalAlign: "middle" }}
          >
            {row[name]}
          </SoftBox>
        </TableCell>
      );
    });

    return (
      <TableRow
        key={rowKey}
        sx={{
          '&:last-child td, &:last-child th': noEndBorder ? { border: 0 } : {},
        }}
      >
        {tableRow}
      </TableRow>
    );
  });

  return useMemo(
    () => (
      <TableContainer>
        <MuiTable>
          <SoftBox component="thead">
            <TableRow>{renderColumns}</TableRow>
          </SoftBox>
          <TableBody>{renderRows}</TableBody>
        </MuiTable>
      </TableContainer>
    ),
    [columns, rows]
  );
};

export default Table; 